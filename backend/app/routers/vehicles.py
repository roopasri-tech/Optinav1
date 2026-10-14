from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.models import Vehicle
from app.schemas import VehicleCreate, VehicleUpdate
from app.services.vehicle_service import (
    create_vehicle, delete_vehicle, get_vehicle, list_vehicles, range_summary, to_spec, update_vehicle,
)
from app.utils.errors import NotFound

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _vehicle_dict(v: Vehicle) -> dict:
    return {
        "id": v.id, "name": v.name, "vehicle_type": v.vehicle_type, "fuel_type": v.fuel_type,
        "secondary_fuel_type": v.secondary_fuel_type,
        "tank_capacity": v.tank_capacity, "efficiency": v.efficiency, "current_fuel_pct": v.current_fuel_pct,
        "cng_tank_capacity": v.cng_tank_capacity, "cng_efficiency": v.cng_efficiency,
        "current_cng_pct": v.current_cng_pct,
        "battery_capacity_kwh": v.battery_capacity_kwh, "ev_efficiency": v.ev_efficiency,
        "current_battery_pct": v.current_battery_pct,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.get("")
def list_all(db: Session = Depends(get_db)):
    return [_vehicle_dict(v) for v in list_vehicles(db)]


@router.get("/{vehicle_id}")
def get_one(vehicle_id: int, db: Session = Depends(get_db)):
    v = get_vehicle(db, vehicle_id)
    if not v:
        raise NotFound("Vehicle not found")
    return _vehicle_dict(v)


@router.post("", status_code=201)
def create_one(body: VehicleCreate, db: Session = Depends(get_db)):
    return _vehicle_dict(create_vehicle(db, body.model_dump()))


@router.put("/{vehicle_id}")
def update_one(vehicle_id: int, body: VehicleUpdate, db: Session = Depends(get_db)):
    v = update_vehicle(db, vehicle_id, body.model_dump(exclude_none=True))
    if not v:
        raise NotFound("Vehicle not found")
    return _vehicle_dict(v)


@router.delete("/{vehicle_id}", status_code=204)
def delete_one(vehicle_id: int, db: Session = Depends(get_db)):
    if not delete_vehicle(db, vehicle_id):
        raise NotFound("Vehicle not found")
    return Response(status_code=204)


@router.get("/{vehicle_id}/range")
def vehicle_range(vehicle_id: int,
                  current_fuel_pct: Optional[float] = Query(None, ge=0, le=100),
                  current_cng_pct: Optional[float] = Query(None, ge=0, le=100),
                  current_battery_pct: Optional[float] = Query(None, ge=0, le=100),
                  db: Session = Depends(get_db)):
    """Usable range = capacity x level x efficiency x safety factor (per fuel)."""
    v = get_vehicle(db, vehicle_id)
    if not v:
        raise NotFound("Vehicle not found")
    overrides = {k: val for k, val in {"current_fuel_pct": current_fuel_pct, "current_cng_pct": current_cng_pct,
                                       "current_battery_pct": current_battery_pct}.items() if val is not None}
    return range_summary(to_spec(v, overrides))
