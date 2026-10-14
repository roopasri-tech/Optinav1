from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas import RoutePlanRequest
from app.services.optimization_service import load_route, route_to_dict, save_route
from app.services.route_service import plan_route

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/plan")
async def plan(body: RoutePlanRequest, db: Session = Depends(get_db)):
    """Road route between two places (OSRM). Distance in km, duration in whole minutes."""
    data = await plan_route(body.source.query, body.source.lat, body.source.lon,
                            body.destination.query, body.destination.lat, body.destination.lon)
    return route_to_dict(save_route(db, data))


@router.get("/{route_id}")
def get_route(route_id: int, db: Session = Depends(get_db)):
    return route_to_dict(load_route(db, route_id))
