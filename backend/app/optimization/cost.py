"""Small, explicit cost/energy formulas used everywhere."""
from typing import Dict, List, Optional, Tuple

from app.config.settings import settings
from app.optimization.state import FuelSpec


def units_for_distance(distance_km: float, f: FuelSpec) -> float:
    """fuel_needed = distance / efficiency  (expected consumption)."""
    return distance_km / f.efficiency


def fuel_cost(units: float, f: FuelSpec) -> float:
    """fuel_cost = fuel_needed x price_per_unit"""
    return units * f.price_per_unit


def charging_minutes(kwh: float, charger_kw: Optional[float]) -> float:
    """Minutes to add `kwh` at a charger (power capped at a typical car's 60 kW DC limit)."""
    power = min(charger_kw or settings.EV_DEFAULT_POWER_KW, 60.0)
    power = max(power, 3.3)
    return kwh / (power * settings.EV_CHARGE_EFFICIENCY) * 60.0


def drive_cheapest_first(
    units: List[float], fuels: List[FuelSpec], distance_km: float, conservative: bool
) -> Tuple[Optional[List[float]], Dict[str, float]]:
    """Drive `distance_km` burning the cheapest fuel first (fuels are pre-sorted).

    conservative=True  -> uses efficiency x SAFETY_FACTOR (feasibility planning)
    conservative=False -> uses rated efficiency (expected consumption)

    Returns (remaining_units, km_per_fuel); remaining_units is None when the
    energy on board is not enough.
    """
    left = list(units)
    km_by_fuel: Dict[str, float] = {}
    remaining = distance_km
    for i, f in enumerate(fuels):
        if remaining <= 1e-9:
            break
        kpu = f.planning_km_per_unit if conservative else f.efficiency
        can = left[i] * kpu
        use = min(can, remaining)
        if use > 0:
            left[i] = max(0.0, left[i] - use / kpu)
            km_by_fuel[f.fuel_type] = km_by_fuel.get(f.fuel_type, 0.0) + use
            remaining -= use
    if remaining > 1e-6:
        return None, km_by_fuel
    return left, km_by_fuel


def cost_of_km(km_by_fuel: Dict[str, float], fuels: List[FuelSpec]) -> float:
    by_type = {f.fuel_type: f for f in fuels}
    return sum(km * by_type[ft].cost_per_km for ft, km in km_by_fuel.items())
