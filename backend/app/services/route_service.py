"""Place search, geocoding and road routing.

Routing comes ONLY from a real road router (OSRM). If both OSRM servers fail we
return a clear error - we never present a straight-line estimate as a road distance.
"""
import asyncio
import logging
import time
from collections import OrderedDict
from typing import List, Optional, Tuple

import httpx

from app.config.settings import settings
from app.utils.errors import ExternalServiceError, SmartRouteError
from app.utils.geo import cumulative_km, decimate, haversine_km, in_india

logger = logging.getLogger(__name__)

# Offline list of major cities, used ONLY when the online geocoders are unreachable.
# Coordinates are city centres. States are deliberately not listed so that
# "Kerala" is never silently turned into a point.
OFFLINE_CITIES = {
    "hyderabad": (17.3850, 78.4867, "Telangana"), "secunderabad": (17.4399, 78.4983, "Telangana"),
    "warangal": (17.9689, 79.5941, "Telangana"), "kochi": (9.9312, 76.2673, "Kerala"),
    "ernakulam": (9.9816, 76.2999, "Kerala"), "thiruvananthapuram": (8.5241, 76.9366, "Kerala"),
    "kozhikode": (11.2588, 75.7804, "Kerala"), "thrissur": (10.5276, 76.2144, "Kerala"),
    "bengaluru": (12.9716, 77.5946, "Karnataka"), "bangalore": (12.9716, 77.5946, "Karnataka"),
    "mysuru": (12.2958, 76.6394, "Karnataka"), "mangaluru": (12.9141, 74.8560, "Karnataka"),
    "hubballi": (15.3647, 75.1240, "Karnataka"), "chennai": (13.0827, 80.2707, "Tamil Nadu"),
    "coimbatore": (11.0168, 76.9558, "Tamil Nadu"), "madurai": (9.9252, 78.1198, "Tamil Nadu"),
    "mumbai": (19.0760, 72.8777, "Maharashtra"), "pune": (18.5204, 73.8567, "Maharashtra"),
    "nagpur": (21.1458, 79.0882, "Maharashtra"), "nashik": (19.9975, 73.7898, "Maharashtra"),
    "delhi": (28.6139, 77.2090, "Delhi"), "new delhi": (28.6139, 77.2090, "Delhi"),
    "jammu": (32.7266, 74.8570, "Jammu and Kashmir"), "srinagar": (34.0837, 74.7973, "Jammu and Kashmir"),
    "kolkata": (22.5726, 88.3639, "West Bengal"), "ahmedabad": (23.0225, 72.5714, "Gujarat"),
    "surat": (21.1702, 72.8311, "Gujarat"), "vadodara": (22.3072, 73.1812, "Gujarat"),
    "jaipur": (26.9124, 75.7873, "Rajasthan"), "udaipur": (24.5854, 73.7125, "Rajasthan"),
    "lucknow": (26.8467, 80.9462, "Uttar Pradesh"), "agra": (27.1767, 78.0081, "Uttar Pradesh"),
    "varanasi": (25.3176, 82.9739, "Uttar Pradesh"), "bhopal": (23.2599, 77.4126, "Madhya Pradesh"),
    "indore": (22.7196, 75.8577, "Madhya Pradesh"), "patna": (25.5941, 85.1376, "Bihar"),
    "visakhapatnam": (17.6868, 83.2185, "Andhra Pradesh"), "vijayawada": (16.5062, 80.6480, "Andhra Pradesh"),
    "tirupati": (13.6288, 79.4192, "Andhra Pradesh"), "chandigarh": (30.7333, 76.7794, "Chandigarh"),
    "amritsar": (31.6340, 74.8723, "Punjab"), "ludhiana": (30.9010, 75.8573, "Punjab"),
    "dehradun": (30.3165, 78.0322, "Uttarakhand"), "bhubaneswar": (20.2961, 85.8245, "Odisha"),
    "raipur": (21.2514, 81.6296, "Chhattisgarh"), "ranchi": (23.3441, 85.3096, "Jharkhand"),
    "guwahati": (26.1445, 91.7362, "Assam"), "panaji": (15.4909, 73.8278, "Goa"),
    "shimla": (31.1048, 77.1734, "Himachal Pradesh"),
}

_REGION_TYPES = {"state", "country", "region", "province"}

_search_cache: "OrderedDict[str, Tuple[float, list]]" = OrderedDict()
_CACHE_SECONDS = 3600
_nominatim_lock = asyncio.Lock()
_nominatim_last = 0.0


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0),
                             headers={"User-Agent": settings.HTTP_USER_AGENT})


def _photon_label(p: dict) -> Tuple[str, str]:
    name = p.get("name") or p.get("street") or p.get("city") or ""
    parts = [name]
    for k in ("city", "district", "state"):
        v = p.get(k)
        if v and v not in parts:
            parts.append(v)
    return parts[0], ", ".join(x for x in parts if x)


async def _photon(query: str, limit: int) -> List[dict]:
    params = {"q": query, "limit": limit * 2, "lang": "en", "bbox": "68.0,6.0,97.6,37.6"}
    async with _client(settings.GEOCODER_TIMEOUT) as c:
        r = await c.get(settings.PHOTON_URL, params=params)
        r.raise_for_status()
        data = r.json()
    out = []
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        if p.get("countrycode", "").upper() not in ("IN", ""):
            continue
        lon, lat = feat.get("geometry", {}).get("coordinates", [None, None])[:2]
        if lat is None or not in_india(lat, lon):
            continue
        name, label = _photon_label(p)
        # Photon "type": house | street | locality | district | city | county | state | country | other
        kind = p.get("type") or p.get("osm_value") or "place"
        out.append({"name": name, "label": label, "lat": round(lat, 6), "lon": round(lon, 6),
                    "kind": kind, "state": p.get("state"), "source": "photon"})
        if len(out) >= limit:
            break
    return out


async def _nominatim(query: str, limit: int) -> List[dict]:
    """One-off lookup, max 1 request/second as required by the Nominatim usage policy."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = 1.0 - (time.monotonic() - _nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _nominatim_last = time.monotonic()
        async with _client(settings.GEOCODER_TIMEOUT) as c:
            r = await c.get(settings.NOMINATIM_URL, params={
                "q": query, "format": "jsonv2", "limit": limit, "countrycodes": "in", "addressdetails": 1})
            r.raise_for_status()
            data = r.json()
    out = []
    for d in data:
        lat, lon = float(d["lat"]), float(d["lon"])
        if not in_india(lat, lon):
            continue
        addr = d.get("address", {})
        name = d.get("name") or d.get("display_name", "").split(",")[0]
        state = addr.get("state")
        label = ", ".join(x for x in [name, addr.get("state_district") or addr.get("county"), state] if x)
        kind = d.get("addresstype") or d.get("type") or "place"
        out.append({"name": name, "label": label, "lat": round(lat, 6), "lon": round(lon, 6),
                    "kind": kind, "state": state, "source": "nominatim"})
    return out


def _offline(query: str, limit: int) -> List[dict]:
    q = query.strip().lower()
    out = []
    for key, (lat, lon, state) in OFFLINE_CITIES.items():
        if key.startswith(q) or q == key:
            out.append({"name": key.title(), "label": f"{key.title()}, {state}", "lat": lat, "lon": lon,
                        "kind": "city", "state": state, "source": "offline"})
    return out[:limit]


async def search_places(query: str, limit: int = 6) -> List[dict]:
    """Autocomplete search restricted to India. Photon -> Nominatim -> offline list."""
    q = " ".join(query.split())
    if len(q) < 2:
        return []
    ck = f"{q.lower()}|{limit}"
    hit = _search_cache.get(ck)
    if hit and time.time() - hit[0] < _CACHE_SECONDS:
        return hit[1]

    results: List[dict] = []
    for provider in (_photon, _nominatim):
        try:
            results = await provider(q, limit)
            if results:
                break
        except Exception as e:  # provider down / rate-limited: try the next one
            logger.warning("Place search via %s failed: %s", provider.__name__, type(e).__name__)
    if not results:
        results = _offline(q, limit)

    _search_cache[ck] = (time.time(), results)
    while len(_search_cache) > 500:
        _search_cache.popitem(last=False)
    return results


async def geocode(query: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Tuple[float, float, str]:
    """Resolve a location. Coordinates chosen in the UI are used exactly as selected."""
    label = (query or "").strip()
    if lat is not None and lon is not None:
        if not in_india(lat, lon):
            raise SmartRouteError(f"'{label or 'Selected point'}' is outside India. SmartRoute plans trips within India.")
        return float(lat), float(lon), label or f"{lat:.4f}, {lon:.4f}"
    if not label:
        raise SmartRouteError("Please choose a start and a destination.")
    results = await search_places(label, limit=3)
    if not results:
        raise SmartRouteError(f"Could not find '{label}' in India. Please pick a place from the suggestions.")
    best = results[0]
    if best["kind"] in _REGION_TYPES:
        raise SmartRouteError(f"'{best['label']}' is a {best['kind']}, not a specific place. "
                              "Please choose a city, town or address.")
    return best["lat"], best["lon"], best["label"]


async def _osrm(base: str, s_lat: float, s_lon: float, d_lat: float, d_lon: float) -> dict:
    url = f"{base.rstrip('/')}/route/v1/driving/{s_lon:.6f},{s_lat:.6f};{d_lon:.6f},{d_lat:.6f}"
    async with _client(settings.OSRM_TIMEOUT) as c:
        r = await c.get(url, params={"overview": "full", "geometries": "geojson", "steps": "false"})
        if r.status_code == 400:
            data = r.json()
            raise SmartRouteError("No road route could be found between these places."
                                  if data.get("code") in ("NoRoute", "NoSegment") else "Invalid route request.")
        r.raise_for_status()
        data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise SmartRouteError("No road route could be found between these places.")
    return data


async def get_route(s_lat: float, s_lon: float, d_lat: float, d_lon: float) -> dict:
    """Road route from OSRM: distance (km), duration (whole minutes), geometry [[lat, lon], ...]."""
    if haversine_km(s_lat, s_lon, d_lat, d_lon) < 0.3:
        raise SmartRouteError("Start and destination are the same place.")

    data = None
    last_error: Optional[Exception] = None
    for base in (settings.OSRM_BASE_URL, settings.OSRM_FALLBACK_URL):
        if not base:
            continue
        try:
            data = await _osrm(base, s_lat, s_lon, d_lat, d_lon)
            break
        except SmartRouteError:
            raise
        except Exception as e:
            last_error = e
            logger.warning("OSRM server %s failed: %s", base, type(e).__name__)
    if data is None:
        logger.error("All routing servers failed: %s", last_error)
        raise ExternalServiceError("The road-routing service is unavailable right now, so a driving distance "
                                   "cannot be calculated. Please try again in a minute.")

    route = data["routes"][0]
    # Sanity check: the router must have matched our points to nearby roads.
    for wp, (lat, lon), what in zip(data.get("waypoints", []), [(s_lat, s_lon), (d_lat, d_lon)],
                                    ["start", "destination"]):
        snapped = wp.get("distance", 0) / 1000.0
        if snapped > 25:
            raise SmartRouteError(f"The selected {what} is {snapped:.0f} km from the nearest road. "
                                  "Please choose a more specific place.")

    coords = [(c[1], c[0]) for c in route.get("geometry", {}).get("coordinates", [])]
    if len(coords) < 2:
        raise ExternalServiceError("The routing service returned an empty route. Please try again.")
    if haversine_km(coords[-1][0], coords[-1][1], d_lat, d_lon) > 30 or \
            haversine_km(coords[0][0], coords[0][1], s_lat, s_lon) > 30:
        raise ExternalServiceError("The routing service returned a route that does not match the selected "
                                   "places. Please try again.")

    distance_km = route["distance"] / 1000.0
    geometry = decimate(coords, min_step_km=0.4, max_points=5000)
    # The decimated polyline must still describe the same road (within a few %).
    path_km = cumulative_km(geometry)[-1]
    if distance_km > 1 and abs(path_km - distance_km) / distance_km > 0.08:
        logger.warning("Geometry length %.1f km differs from route distance %.1f km", path_km, distance_km)

    return {
        "distance_km": round(distance_km, 1),
        "duration_min": int(round(route["duration"] / 60.0)),
        "geometry": [[round(a, 6), round(b, 6)] for a, b in geometry],
        "provider": "osrm",
    }


async def plan_route(source_query: str, source_lat: Optional[float], source_lon: Optional[float],
                     dest_query: str, dest_lat: Optional[float], dest_lon: Optional[float]) -> dict:
    s_lat, s_lon, s_name = await geocode(source_query, source_lat, source_lon)
    d_lat, d_lon, d_name = await geocode(dest_query, dest_lat, dest_lon)
    route = await get_route(s_lat, s_lon, d_lat, d_lon)
    return {"source_name": s_name, "source_lat": s_lat, "source_lon": s_lon,
            "dest_name": d_name, "dest_lat": d_lat, "dest_lon": d_lon, **route}
