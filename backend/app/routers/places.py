import math
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.session import get_db
from app.models.models import Facility
from app.schemas import NearRouteRequest
from app.services.facility_service import CATEGORIES, SOURCE_LABEL, get_corridor
from app.services.optimization_service import load_route, route_coords
from app.services.route_service import search_places
from app.utils.errors import SmartRouteError
from app.utils.geo import cumulative_km, haversine_km, in_india

router = APIRouter(prefix="/api", tags=["places"])


def _check_category(category: Optional[str]) -> Optional[str]:
    if category in (None, "", "all"):
        return None
    if category not in CATEGORIES:
        raise SmartRouteError(f"Unknown category '{category}'. Use one of: {', '.join(CATEGORIES)}.")
    return category


def _filter(items: List[dict], category: Optional[str]) -> List[dict]:
    if not category:
        return items
    if category == "cng":
        return [f for f in items if f["category"] == "fuel" and "cng" in (f.get("fuel_types") or [])]
    return [f for f in items if f["category"] == category]


@router.get("/places/search")
async def places_search(q: str = Query(..., min_length=2, max_length=200), limit: int = Query(6, ge=1, le=10)):
    """Autocomplete for places in India (Photon, with Nominatim / offline fallback)."""
    return {"results": await search_places(q, limit)}


async def _corridor_response(db: Session, coords, total_km: float, category: Optional[str], wait: bool,
                             route_id: Optional[int]) -> dict:
    data = await get_corridor(db, coords, total_km, settings.NEAR_ROUTE_WAIT_SECONDS if wait else 0,
                              cap=settings.MAX_FACILITIES_PER_CATEGORY)
    items = _filter(data["facilities"], category)
    return {"route_id": route_id, "facilities": items, "total": len(items), "counts": data["counts"],
            "coverage": data["coverage"], "sources": data["sources"], "warnings": data["warnings"]}


@router.post("/places/near-route")
async def near_route(body: NearRouteRequest, db: Session = Depends(get_db)):
    """Facilities along a route corridor (OpenStreetMap / Open Charge Map).
    While `coverage.complete` is false, call again to receive the remaining sections."""
    category = _check_category(body.category)
    if body.route_id is not None:
        route = load_route(db, body.route_id)
        coords, total_km = route_coords(route), route.distance_km
    else:
        coords = [(p[0], p[1]) for p in body.geometry]
        if not all(in_india(a, b) for a, b in coords[:: max(1, len(coords) // 50)]):
            raise SmartRouteError("Route geometry must be inside India.")
        total_km = body.distance_km or cumulative_km(coords)[-1]
    return await _corridor_response(db, coords, total_km, category, body.wait, body.route_id)


@router.get("/places/near-route")
async def near_route_get(
    route_id: Optional[int] = Query(None, description="Facilities along a planned route"),
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: float = Query(5.0, gt=0, le=50),
    category: Optional[str] = Query(None),
    wait: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Either `route_id` (corridor search) or `lat`+`lon` (cached facilities around a point)."""
    category = _check_category(category)
    if route_id is not None:
        route = load_route(db, route_id)
        return await _corridor_response(db, route_coords(route), route.distance_km, category, wait, route_id)
    if lat is None or lon is None:
        raise SmartRouteError("Give route_id, or lat and lon.")
    pad_lat = radius_km / 110.574
    pad_lon = radius_km / (111.32 * max(0.2, math.cos(math.radians(lat))))
    q = db.query(Facility).filter(Facility.latitude.between(lat - pad_lat, lat + pad_lat),
                                  Facility.longitude.between(lon - pad_lon, lon + pad_lon),
                                  Facility.is_operational.is_(True))
    if category:
        q = q.filter(Facility.category == ("fuel" if category == "cng" else category))
    out = []
    for f in q.limit(2000).all():
        d = haversine_km(lat, lon, f.latitude, f.longitude)
        if d <= radius_km and (category != "cng" or "cng" in (f.fuel_types or [])):
            out.append({**_fac(f), "distance_km": round(d, 2)})
    out.sort(key=lambda x: x["distance_km"])
    return {"facilities": out[:300], "total": len(out)}


def _fac(f: Facility) -> dict:
    return {"id": f.id, "name": f.name, "category": f.category, "latitude": f.latitude, "longitude": f.longitude,
            "address": f.address or "", "fuel_types": f.fuel_types or [], "connector_types": f.connector_types or [],
            "charging_power_kw": f.charging_power_kw, "source": f.source,
            "source_label": SOURCE_LABEL.get(f.source, f.source), "extra": f.extra or {}}


def _list(db: Session, categories, limit: int, offset: int, cng_only: bool = False) -> List[dict]:
    q = db.query(Facility).filter(Facility.category.in_(categories), Facility.is_operational.is_(True))
    rows = q.order_by(Facility.id).offset(offset).limit(limit * (5 if cng_only else 1)).all()
    out = [_fac(f) for f in rows if not cng_only or "cng" in (f.fuel_types or [])]
    return out[:limit]


@router.get("/stations")
def get_stations(cng_only: bool = False, limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db)):
    """Fuel stations stored from previous route lookups (OpenStreetMap)."""
    return _list(db, ["fuel"], limit, offset, cng_only)


@router.get("/chargers")
def get_chargers(limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return _list(db, ["ev"], limit, offset)


@router.get("/restaurants")
def get_restaurants(limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return _list(db, ["restaurant"], limit, offset)


@router.get("/amenities")
def get_amenities(category: Optional[str] = None, limit: int = Query(500, ge=1, le=5000),
                  offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    cats = [category] if category in ("parking", "restroom") else ["parking", "restroom"]
    return _list(db, cats, limit, offset)
