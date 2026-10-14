from typing import List, Optional

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.models import Vehicle
from app.optimization.state import EFF_UNIT, LABEL, UNIT, FuelSpec, VehicleSpec
from app.utils.errors import SmartRouteError

FUEL_TYPES = ("petrol", "diesel", "cng", "electric", "bifuel")
_ALIASES = {"bifuel_cng_petrol": "bifuel", "cng_petrol": "bifuel", "bi-fuel": "bifuel", "ev": "electric"}


def normalise_fuel_type(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    v = _ALIASES.get(v, v)
    if v not in FUEL_TYPES:
        raise SmartRouteError(f"Unknown fuel type '{value}'. Use one of: petrol, diesel, cng, electric, bifuel.")
    return v


def _require_positive(data: dict, *fields: str) -> None:
    for name in fields:
        val = data.get(name)
        if val is None or val <= 0:
            pretty = name.replace("_", " ")
            raise SmartRouteError(f"'{pretty}' must be a positive number for this fuel type.")


def validate_vehicle_data(data: dict) -> dict:
    """Make sure the fields needed for range calculation exist for the chosen fuel type."""
    data = dict(data)
    data["fuel_type"] = normalise_fuel_type(data.get("fuel_type"))
    ft = data["fuel_type"]
    if ft in ("petrol", "diesel", "cng"):
        _require_positive(data, "tank_capacity", "efficiency")
    elif ft == "bifuel":
        _require_positive(data, "tank_capacity", "efficiency", "cng_tank_capacity", "cng_efficiency")
        data["secondary_fuel_type"] = "petrol"
        if data.get("current_cng_pct") is None:
            data["current_cng_pct"] = 100.0
    elif ft == "electric":
        _require_positive(data, "battery_capacity_kwh", "ev_efficiency")
        if data.get("current_battery_pct") is None:
            data["current_battery_pct"] = 100.0
        # The liquid-fuel columns are NOT NULL in the schema but unused for EVs.
        data["tank_capacity"] = data.get("tank_capacity") or data["battery_capacity_kwh"]
        data["efficiency"] = data.get("efficiency") or data["ev_efficiency"]
    return data


def list_vehicles(db: Session) -> List[Vehicle]:
    return db.query(Vehicle).order_by(Vehicle.id).all()


def get_vehicle(db: Session, vehicle_id: int) -> Optional[Vehicle]:
    return db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()


def create_vehicle(db: Session, data: dict) -> Vehicle:
    v = Vehicle(**validate_vehicle_data(data))
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def update_vehicle(db: Session, vehicle_id: int, data: dict) -> Optional[Vehicle]:
    v = get_vehicle(db, vehicle_id)
    if not v:
        return None
    merged = {c.name: getattr(v, c.name) for c in Vehicle.__table__.columns
              if c.name not in ("id", "created_at", "updated_at")}
    merged.update({k: val for k, val in data.items() if val is not None})
    merged = validate_vehicle_data(merged)
    for k, val in merged.items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return v


def delete_vehicle(db: Session, vehicle_id: int) -> bool:
    v = get_vehicle(db, vehicle_id)
    if not v:
        return False
    db.delete(v)   # old trip plans keep their data; their vehicle_id becomes NULL
    db.commit()
    return True


def _level(override: Optional[float], stored: Optional[float]) -> float:
    """Pick the trip-specific level if given, else the stored one. 0 % is a valid level."""
    value = override if override is not None else stored
    if value is None:
        value = 100.0
    return max(0.0, min(100.0, float(value)))


def default_prices(overrides: dict) -> dict:
    return {
        "petrol": overrides.get("petrol_price") or settings.PETROL_PRICE,
        "diesel": overrides.get("diesel_price") or settings.DIESEL_PRICE,
        "cng": overrides.get("cng_price") or settings.CNG_PRICE,
        "electric": overrides.get("electricity_price") or settings.ELECTRICITY_PRICE,
    }


def to_spec(v: Vehicle, overrides: Optional[dict] = None) -> VehicleSpec:
    """Convert a stored vehicle (+ trip-specific levels/prices) into a planning spec."""
    overrides = overrides or {}
    prices = default_prices(overrides)
    ft = normalise_fuel_type(v.fuel_type)
    fuels: List[FuelSpec] = []

    if ft == "electric":
        fuels.append(FuelSpec("electric", v.battery_capacity_kwh, _level(overrides.get("current_battery_pct"),
                              v.current_battery_pct), v.ev_efficiency, prices["electric"],
                              max_fill_pct=settings.EV_MAX_CHARGE_PCT))
    elif ft == "bifuel":
        fuels.append(FuelSpec("cng", v.cng_tank_capacity, _level(overrides.get("current_cng_pct"), v.current_cng_pct),
                              v.cng_efficiency, prices["cng"]))
        fuels.append(FuelSpec("petrol", v.tank_capacity, _level(overrides.get("current_fuel_pct"), v.current_fuel_pct),
                              v.efficiency, prices["petrol"]))
    else:
        fuels.append(FuelSpec(ft, v.tank_capacity, _level(overrides.get("current_fuel_pct"), v.current_fuel_pct),
                              v.efficiency, prices[ft]))

    for f in fuels:
        if not f.capacity or f.capacity <= 0 or not f.efficiency or f.efficiency <= 0:
            raise SmartRouteError(f"Vehicle '{v.name}' has an invalid {LABEL[f.fuel_type]} capacity or efficiency. "
                                  "Please edit the vehicle.")
    fuels.sort(key=lambda f: f.cost_per_km)   # cheapest per km is burnt first
    return VehicleSpec(vehicle_id=v.id, name=v.name, vehicle_type=v.vehicle_type or "car", fuels=fuels)


def range_summary(spec: VehicleSpec) -> dict:
    """Everything the UI needs to explain the vehicle's range."""
    return {
        "vehicle_id": spec.vehicle_id,
        "name": spec.name,
        "safety_factor": settings.SAFETY_FACTOR,
        "total_usable_range_km": round(spec.total_usable_range_km, 1),
        "fuels": [
            {
                "fuel_type": f.fuel_type,
                "label": LABEL[f.fuel_type],
                "capacity": f.capacity,
                "unit": UNIT[f.fuel_type],
                "current_pct": round(f.current_pct, 1),
                "current_units": round(f.current_units, 2),
                "efficiency": f.efficiency,
                "efficiency_unit": EFF_UNIT[f.fuel_type],
                "price_per_unit": f.price_per_unit,
                "cost_per_km": round(f.cost_per_km, 2),
                "usable_range_km": round(f.usable_range_km, 1),
                "refill_range_km": round(f.refill_range_km, 1),
                "max_fill_pct": f.max_fill_pct,
            }
            for f in spec.fuels
        ],
    }
