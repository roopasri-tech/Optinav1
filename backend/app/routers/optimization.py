from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.models import TripPlan, TripStop
from app.schemas import OptimizationRequest
from app.services.optimization_service import optimize_trip, route_to_dict
from app.utils.errors import NotFound

router = APIRouter(prefix="/api", tags=["optimization"])

_OVERRIDE_FIELDS = ("current_fuel_pct", "current_cng_pct", "current_battery_pct",
                    "petrol_price", "diesel_price", "cng_price", "electricity_price")


@router.post("/optimization/trip")
async def run_optimization(body: OptimizationRequest, db: Session = Depends(get_db)):
    """Plan refuelling/charging stops. Returns feasible=false with an explanation when the
    trip cannot be completed with the verified stations found - never a ₹0 plan."""
    overrides = {k: getattr(body, k) for k in _OVERRIDE_FIELDS if getattr(body, k) is not None}
    return await optimize_trip(
        db, vehicle_id=body.vehicle_id, route_id=body.route_id,
        source=body.source.model_dump() if body.source else None,
        destination=body.destination.model_dump() if body.destination else None,
        overrides=overrides, preference=body.preference)


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    plan = db.query(TripPlan).filter(TripPlan.id == trip_id).first()
    if not plan:
        raise NotFound("Trip not found")
    details = dict(plan.details or {})
    details.update(trip_id=plan.id, route=route_to_dict(plan.route),
                   created_at=plan.created_at.isoformat() if plan.created_at else None)
    return details


@router.get("/trips/{trip_id}/stops")
def get_trip_stops(trip_id: int, db: Session = Depends(get_db)):
    if not db.query(TripPlan.id).filter(TripPlan.id == trip_id).first():
        raise NotFound("Trip not found")
    stops = db.query(TripStop).filter(TripStop.trip_plan_id == trip_id).order_by(TripStop.stop_order, TripStop.id).all()
    return [{"id": s.id, "stop_order": s.stop_order, "stop_type": s.stop_type, "fuel_type": s.fuel_type,
             "quantity": s.quantity, "cost_inr": s.cost_inr, "detour_km": s.detour_km, "reason": s.reason,
             "latitude": s.latitude, "longitude": s.longitude, "name": s.name, "facility_id": s.facility_id}
            for s in stops]
