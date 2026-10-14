"""Trip optimisation pipeline: route -> vehicle range -> facilities -> stop plan -> checks."""
import logging
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.models import Route, TripPlan, TripStop
from app.optimization.solver import PlanIntegrityError, naive_plan, plan_trip
from app.optimization.state import LABEL, Candidate, PlanResult, VehicleSpec
from app.services.facility_service import get_corridor
from app.services.route_service import plan_route
from app.services.vehicle_service import get_vehicle, range_summary, to_spec
from app.utils.errors import NotFound, SmartRouteError

logger = logging.getLogger(__name__)


# ─── Route helpers ────────────────────────────────────────────────────────────

def route_to_dict(r: Route) -> dict:
    coords = (r.geometry or {}).get("coordinates", [])
    return {
        "id": r.id,
        "source": {"label": r.source_name, "lat": r.source_lat, "lon": r.source_lon},
        "destination": {"label": r.destination_name, "lat": r.dest_lat, "lon": r.dest_lon},
        "source_name": r.source_name, "destination_name": r.destination_name,
        "distance_km": round(r.distance_km, 1), "duration_min": int(round(r.duration_min)),
        "geometry": [[c[1], c[0]] for c in coords], "provider": r.provider,
    }


def save_route(db: Session, data: dict) -> Route:
    r = Route(source_name=data["source_name"][:200], destination_name=data["dest_name"][:200],
              source_lat=data["source_lat"], source_lon=data["source_lon"],
              dest_lat=data["dest_lat"], dest_lon=data["dest_lon"],
              distance_km=data["distance_km"], duration_min=data["duration_min"],
              geometry={"type": "LineString", "coordinates": [[p[1], p[0]] for p in data["geometry"]]},
              provider=data.get("provider", "osrm"))
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def load_route(db: Session, route_id: int) -> Route:
    r = db.query(Route).filter(Route.id == route_id).first()
    if not r:
        raise NotFound("Route not found. Please plan the route again.")
    return r


def route_coords(r: Route) -> List[Tuple[float, float]]:
    return [(c[1], c[0]) for c in (r.geometry or {}).get("coordinates", [])]


# ─── Candidates ───────────────────────────────────────────────────────────────

def build_candidates(facilities: List[dict], spec: VehicleSpec) -> List[Candidate]:
    out = []
    for f in facilities:
        if f["category"] == "fuel" and not spec.is_ev:
            fuels = [ft for ft in f.get("fuel_types") or [] if ft in spec.fuel_types]
        elif f["category"] == "ev" and spec.is_ev:
            car_ok = (f.get("extra") or {}).get("car_compatible", True)
            fuels = ["electric"] if (car_ok or spec.vehicle_type in ("bike", "scooter")) else []
        else:
            fuels = []
        if fuels:
            out.append(Candidate(f["id"], f["name"], f["latitude"], f["longitude"], f["km_along"],
                                 f["detour_km"], fuels, f.get("charging_power_kw"), f.get("source", "osm"),
                                 f.get("address", "")))
    return out


def _station_word(spec: VehicleSpec) -> str:
    if spec.is_ev:
        return "EV charging stations"
    if spec.is_bifuel:
        return "CNG or petrol stations"
    return f"{LABEL[spec.fuels[0].fuel_type]} stations"


# ─── Result formatting ────────────────────────────────────────────────────────

def _plan_dict(plan: PlanResult, fac_by_id: Dict[int, dict]) -> dict:
    stops = []
    for s in plan.stops:
        d = asdict(s)
        fac = fac_by_id.get(s.facility_id, {})
        d["fuel_types_inferred"] = fac.get("fuel_types_inferred", False)
        d["source_label"] = fac.get("source_label", s.source)
        d["extra"] = fac.get("extra", {})
        d["cost_inr"] = round(sum(p.cost_inr for p in s.purchases), 2)
        stops.append(d)
    return {
        "feasible": plan.feasible,
        "stops": stops,
        "legs": [asdict(l) for l in plan.legs],
        "energy_cost_inr": plan.energy_cost_inr,
        "total_cost_inr": plan.energy_cost_inr,          # kept for older clients
        "purchase_cost_inr": plan.purchase_cost_inr,
        "fuel_breakdown": plan.fuel_breakdown,
        "driven_km": plan.driven_km,
        "stop_minutes": plan.stop_minutes,
        "arrival_pct": plan.arrival_pct,
        "max_reachable_km": plan.max_reachable_km,
        "message": plan.message,
    }


def _safe_plan(total_km: float, spec: VehicleSpec, cands: List[Candidate], preference: str) -> PlanResult:
    try:
        return plan_trip(total_km, spec, cands, preference)
    except PlanIntegrityError as e:
        logger.error("Plan integrity check failed (%s): %s", preference, e)
        return PlanResult(feasible=False, message="SmartRoute could not produce a plan that passes its "
                                                  "safety checks for this trip.")


def _infeasible_message(spec: VehicleSpec, total_km: float, plan: PlanResult, cands: List[Candidate],
                        coverage: dict) -> str:
    rng = spec.total_usable_range_km
    reach = plan.max_reachable_km
    parts = [f"This trip is {total_km:,.0f} km but with the current levels the vehicle's safe range is "
             f"{rng:,.0f} km."]
    if not cands:
        parts.append(f"No verified {_station_word(spec)} were found along this route, so no refuelling stop "
                     "can be planned.")
    else:
        parts.append(f"Using the {len(cands)} verified {_station_word(spec)} found along the route, the "
                     f"vehicle can safely get only to about km {reach:,.0f}.")
        nxt = [c.km_along for c in cands if c.km_along > reach]
        if nxt:
            parts.append(f"The next known station is at km {min(nxt):,.0f}, which is beyond the safe range.")
        else:
            parts.append("No known station exists beyond that point.")
    if coverage.get("sections_pending") or coverage.get("sections_failed"):
        parts.append("Facility data for part of this route is still loading or could not be fetched, so a "
                     "station may exist there - please try again in a minute.")
    return " ".join(parts)


# ─── Main entry point ─────────────────────────────────────────────────────────

async def optimize_trip(db: Session, *, vehicle_id: int, route_id: Optional[int] = None,
                        source: Optional[dict] = None, destination: Optional[dict] = None,
                        overrides: Optional[dict] = None, preference: str = "cheapest") -> dict:
    overrides = overrides or {}
    if preference not in ("cheapest", "fewest_stops"):
        raise SmartRouteError("preference must be 'cheapest' or 'fewest_stops'.")

    vehicle = get_vehicle(db, vehicle_id)
    if not vehicle:
        raise NotFound("Vehicle not found. Please select a vehicle.")
    spec = to_spec(vehicle, overrides)

    # 1. Route: re-use the exact route the user is looking at when we have its id.
    if route_id is not None:
        route = load_route(db, route_id)
    else:
        if not source or not destination:
            raise SmartRouteError("Please choose a start and a destination.")
        data = await plan_route(source.get("query", ""), source.get("lat"), source.get("lon"),
                                destination.get("query", ""), destination.get("lat"), destination.get("lon"))
        route = save_route(db, data)
    coords = route_coords(route)
    total_km = route.distance_km
    if len(coords) < 2 or total_km <= 0:
        raise SmartRouteError("This route has no geometry. Please plan it again.")

    # 2. Range check (before any optimisation).
    usable = spec.total_usable_range_km
    needs_stop = total_km > usable
    range_check = {
        "trip_km": round(total_km, 1), "usable_range_km": round(usable, 1), "needs_stop": needs_stop,
        "explanation": (f"Trip ({total_km:,.0f} km) is longer than the safe range ({usable:,.0f} km): "
                        "at least one refuelling/charging stop is required." if needs_stop else
                        f"Trip ({total_km:,.0f} km) is within the safe range ({usable:,.0f} km): "
                        "no stop is strictly required."),
    }

    # 3. Facilities along the corridor (fuel + EV only; uncapped for the optimiser).
    corridor = await get_corridor(db, coords, total_km, settings.OPTIMIZE_WAIT_SECONDS if needs_stop else 0,
                                  categories=("fuel", "ev"), cap=None)
    facilities = corridor["facilities"]
    fac_by_id = {f["id"]: f for f in facilities}
    cands = build_candidates(facilities, spec)

    # 4. Plans (requested preference + the alternative, so the user sees the trade-off).
    main = _safe_plan(total_km, spec, cands, preference)
    other_pref = "fewest_stops" if preference == "cheapest" else "cheapest"
    other = _safe_plan(total_km, spec, cands, other_pref) if main.feasible and needs_stop else None

    warnings = list(corridor["warnings"]) if needs_stop else []
    result_opt = _plan_dict(main, fac_by_id)
    result_opt["preference"] = preference

    if main.feasible:
        # Baseline: what the same trip would cost without SmartRoute.
        baseline = None
        if spec.is_bifuel:
            petrol = spec.fuels[-1]
            baseline = {"cost_inr": round(main.driven_km * petrol.cost_per_km, 2),
                        "description": f"Same distance driven entirely on {LABEL[petrol.fuel_type].lower()}"}
        else:
            naive = naive_plan(total_km, spec, cands) if main.stops else None
            if naive is not None:
                baseline = {"cost_inr": naive.energy_cost_inr,
                            "description": "Naive refuelling: drive until the reserve and stop at the last "
                                           "station in range, ignoring detours"}
            elif not main.stops:
                baseline = {"cost_inr": main.energy_cost_inr,
                            "description": "No stop needed - cost depends only on distance"}
        savings = savings_pct = None
        if baseline and baseline["cost_inr"] > 0:
            savings = round(baseline["cost_inr"] - main.energy_cost_inr, 2)
            savings_pct = round(100.0 * savings / baseline["cost_inr"], 1)
            if savings > baseline["cost_inr"] or savings_pct >= 100:
                logger.error("Savings sanity check failed: %s vs %s", savings, baseline)
                baseline, savings, savings_pct = None, None, None
        result_opt.update(baseline=baseline, savings_inr=savings, savings_pct=savings_pct)
        if any(s["fuel_types_inferred"] for s in result_opt["stops"]):
            warnings.append("Some recommended stations have no fuel-type tags in OpenStreetMap; petrol/diesel "
                            "availability there is assumed. Check before relying on them.")
    else:
        result_opt["message"] = _infeasible_message(spec, total_km, main, cands, corridor["coverage"])
        result_opt.update(baseline=None, savings_inr=None, savings_pct=None, energy_cost_inr=None,
                          total_cost_inr=None, purchase_cost_inr=None)
        # What the energy for the whole distance would cost (clearly labelled estimate, not a plan).
        result_opt["energy_estimates"] = [
            {"fuel_type": f.fuel_type, "label": LABEL[f.fuel_type],
             "cost_inr": round(total_km * f.cost_per_km, 2),
             "quantity": round(total_km / f.efficiency, 1), "unit": f.unit}
            for f in spec.fuels]

    alternative = None
    if other is not None and other.feasible:
        alternative = {"preference": other_pref, "stops_count": len(other.stops),
                       "energy_cost_inr": other.energy_cost_inr, "purchase_cost_inr": other.purchase_cost_inr,
                       "stop_minutes": other.stop_minutes}

    # 5. Persist.
    plan_row = TripPlan(route_id=route.id, vehicle_id=vehicle.id,
                        strategy=preference if main.feasible else "infeasible",
                        total_cost_inr=main.energy_cost_inr if main.feasible else 0.0,
                        baseline_cost_inr=(result_opt.get("baseline") or {}).get("cost_inr"),
                        savings_inr=result_opt.get("savings_inr"), fuel_breakdown=main.fuel_breakdown)
    db.add(plan_row)
    db.flush()
    for order, s in enumerate(main.stops):
        for p in s.purchases:
            db.add(TripStop(trip_plan_id=plan_row.id, facility_id=s.facility_id, stop_order=order,
                            stop_type="ev" if p.fuel_type == "electric" else "fuel", fuel_type=p.fuel_type,
                            quantity=p.quantity, cost_inr=p.cost_inr, detour_km=s.detour_km, reason=s.reason,
                            latitude=s.latitude, longitude=s.longitude, name=s.name))

    vehicle_info = range_summary(spec)
    vehicle_info.update(fuel_type=vehicle.fuel_type, vehicle_type=vehicle.vehicle_type)
    response = {
        "trip_id": plan_row.id,
        "route": route_to_dict(route),
        "vehicle": vehicle_info,
        "range_check": range_check,
        "optimization": result_opt,
        "alternative": alternative,
        "facilities": {"candidates": len(cands), "coverage": corridor["coverage"], "sources": corridor["sources"]},
        "warnings": warnings,
        "assumptions": {
            "safety_factor": settings.SAFETY_FACTOR,
            "prices": {f.fuel_type: f.price_per_unit for f in spec.fuels},
            "note": (f"Ranges use {int(settings.SAFETY_FACTOR * 100)}% of rated efficiency for safety; costs use "
                     "rated efficiency. Prices are approximate national averages unless you entered your own."),
        },
    }
    plan_row.details = {k: v for k, v in response.items() if k != "route"}
    db.commit()
    return response
