"""Facility discovery along a route corridor.

Sources (real data only)
------------------------
* OpenStreetMap via the Overpass API - fuel (petrol/diesel/CNG), EV chargers,
  restaurants/fast food/cafes, parking, toilets.
* Open Charge Map - EV chargers (only when OPENCHARGEMAP_API_KEY is set).

How a request is served
-----------------------
1. The route is split into ~SECTION_KM sections. Each section is one bounded
   Overpass query using `around:` on a sampled polyline (a true corridor, not a
   huge bounding box).
2. Sections fetched successfully within FACILITY_CACHE_DAYS are not fetched again.
3. Missing sections are fetched in the background (max OVERPASS_CONCURRENCY at
   once, mirrors rotated, one retry on another mirror). The request waits at most
   a few seconds, then answers with what is stored and a `coverage` report; the
   client polls again while sections are still loading. Nothing blocks long
   enough for the proxy to time out.
4. Results are de-duplicated (same OSM id, or same category within ~75 m),
   projected onto the route (km along, km off route, approximate detour) and
   ranked.

Nothing is invented: unnamed places are shown as "Unnamed ...", and fuel types
that are only assumed (station without fuel tags) are flagged as inferred.
"""
import asyncio
import hashlib
import json
import logging
import math
import re
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from sqlalchemy import and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.session import SessionLocal
from app.models.models import Facility, FacilityFetch
from app.utils.geo import (
    RouteProjector, bounding_box, cumulative_km, haversine_km, in_india, sample_along, split_sections,
)

logger = logging.getLogger(__name__)

CATEGORIES = ("fuel", "cng", "ev", "restaurant", "parking", "restroom")
SOURCE_LABEL = {"osm": "OpenStreetMap", "ocm": "Open Charge Map"}
QUERY_VERSION = "v3"
_YES = {"yes", "true", "1"}
_OMC_BRANDS = ("indian oil", "indianoil", "iocl", "hp", "hindustan petroleum", "hpcl", "bharat petroleum",
               "bpcl", "reliance", "jio-bp", "jio bp", "nayara", "essar", "shell")

_OVERPASS_QUERY = """[out:json][timeout:{timeout}];
(
  nwr["amenity"="fuel"](around:{fuel_m},{pts});
  nwr["amenity"="charging_station"](around:{fuel_m},{pts});
  nwr["amenity"~"^(restaurant|fast_food|cafe|food_court)$"](around:{amen_m},{pts});
  nwr["amenity"="parking"](around:{amen_m},{pts});
  nwr["amenity"="toilets"](around:{amen_m},{pts});
);
out center;"""

# Background fetches shared by all requests (keyed by provider + section key).
_inflight: Dict[str, asyncio.Task] = {}
_overpass_sem: Optional[asyncio.Semaphore] = None


def _semaphore() -> asyncio.Semaphore:
    global _overpass_sem
    if _overpass_sem is None:
        _overpass_sem = asyncio.Semaphore(max(1, settings.OVERPASS_CONCURRENCY))
    return _overpass_sem


# ─── OSM tag interpretation ───────────────────────────────────────────────────

def _yes(v: Optional[str]) -> bool:
    return (v or "").strip().lower() in _YES


def detect_fuel_types(tags: dict) -> Tuple[List[str], bool]:
    """Return (fuel_types, inferred). `inferred` is True when the station has no
    fuel tags and we assume the standard Indian pump offering (petrol + diesel)."""
    mapping = [("fuel:petrol", "petrol"), ("fuel:octane_91", "petrol"), ("fuel:octane_95", "petrol"),
               ("fuel:octane_98", "petrol"), ("fuel:e10", "petrol"), ("fuel:e20", "petrol"),
               ("fuel:diesel", "diesel"), ("fuel:HGV_diesel", "diesel"), ("fuel:cng", "cng"),
               ("fuel:lpg", "lpg")]
    found, explicit_no, explicit = set(), set(), False
    for tag, ft in mapping:
        if tag in tags:
            explicit = True
            if _yes(tags[tag]):
                found.add(ft)
            elif tags[tag].strip().lower() == "no":
                explicit_no.add(ft)
    text = " ".join(tags.get(k, "") for k in ("name", "name:en", "brand", "operator")).lower()
    if re.search(r"\bcng\b", text) and "cng" not in explicit_no:
        found.add("cng")
    inferred = False
    if not (found - {"cng", "lpg"}):
        # No liquid fuel tagged. A station of an Indian oil company (or one with
        # no fuel tags at all) is assumed to sell petrol and diesel - flagged as inferred.
        is_omc = any(re.search(rf"\b{re.escape(b)}\b", text) for b in _OMC_BRANDS)
        if is_omc or not explicit and "cng" not in found:
            for ft in ("petrol", "diesel"):
                if ft not in explicit_no:
                    found.add(ft)
                    inferred = True
    order = ["petrol", "diesel", "cng", "lpg"]
    return [ft for ft in order if ft in found], inferred


def _parse_kw(value: str) -> Optional[float]:
    m = re.search(r"([\d.]+)\s*(kw|w)?", value.lower())
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    if m.group(2) == "w" or (m.group(2) is None and n > 1000):
        n /= 1000.0
    return n if 0 < n <= 1000 else None


def _ev_details(tags: dict) -> Tuple[List[str], Optional[float]]:
    names = {"type2_combo": "CCS2", "ccs": "CCS2", "chademo": "CHAdeMO", "type2": "Type 2",
             "type1": "Type 1", "gb_t": "GB/T", "type2_cable": "Type 2", "bharat_ac001": "Bharat AC-001",
             "bharat_dc001": "Bharat DC-001"}
    connectors, power = [], None
    for k, v in tags.items():
        if not k.startswith("socket:"):
            continue
        parts = k.split(":")
        sock = parts[1] if len(parts) > 1 else ""
        if len(parts) == 2 and v.strip().lower() not in ("no", "0"):
            label = names.get(sock, sock.replace("_", " ").title())
            if label not in connectors:
                connectors.append(label)
        if len(parts) == 3 and parts[2] in ("output", "power"):
            kw = _parse_kw(v)
            if kw:
                power = max(power or 0.0, kw)
    for k in ("charging:maxchargingpower", "maxpower", "charging_station:output"):
        if k in tags:
            kw = _parse_kw(tags[k])
            if kw:
                power = max(power or 0.0, kw)
    return connectors, power


def _address(tags: dict) -> str:
    if tags.get("addr:full"):
        return tags["addr:full"]
    parts = [tags.get("addr:housenumber"), tags.get("addr:street"),
             tags.get("addr:city") or tags.get("addr:place") or tags.get("addr:village"),
             tags.get("addr:postcode")]
    return ", ".join(p for p in parts if p)


def normalise_osm(element: dict) -> Optional[dict]:
    """Convert one Overpass element into a facility record (or None to skip it)."""
    tags = element.get("tags") or {}
    lat = element.get("lat", (element.get("center") or {}).get("lat"))
    lon = element.get("lon", (element.get("center") or {}).get("lon"))
    if lat is None or lon is None:
        return None
    lat, lon = float(lat), float(lon)
    if not in_india(lat, lon):
        return None
    amenity = tags.get("amenity", "")
    access = tags.get("access", "").lower()
    if access in ("private", "no"):
        return None
    if tags.get("disused") == "yes" or tags.get("abandoned") == "yes":
        return None

    etype, eid = element.get("type", "node"), element.get("id")
    name = tags.get("name:en") or tags.get("name") or ""
    extra = {k: v for k, v in {
        "brand": tags.get("brand"), "operator": tags.get("operator"),
        "website": tags.get("website") or tags.get("contact:website") or tags.get("url"),
        "phone": tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile"),
        "opening_hours": tags.get("opening_hours"),
        "osm_url": f"https://www.openstreetmap.org/{etype}/{eid}",
    }.items() if v}
    rec = {"external_id": f"osm:{etype}/{eid}", "latitude": lat, "longitude": lon,
           "address": _address(tags)[:400], "source": "osm", "fuel_types": None,
           "connector_types": None, "charging_power_kw": None, "num_chargers": None}

    if amenity == "fuel":
        fuels, inferred = detect_fuel_types(tags)
        extra["fuel_types_inferred"] = inferred
        label = name or tags.get("brand") or tags.get("operator")
        rec.update(category="fuel", fuel_types=fuels,
                   name=label or ("Unnamed CNG station" if fuels == ["cng"] else "Unnamed fuel station"))
    elif amenity == "charging_station":
        connectors, power = _ev_details(tags)
        extra["car_compatible"] = tags.get("motorcar", "").lower() != "no"
        try:
            rec["num_chargers"] = int(tags["capacity"]) if tags.get("capacity", "").isdigit() else None
        except ValueError:
            pass
        rec.update(category="ev", connector_types=connectors, charging_power_kw=power,
                   name=name or tags.get("brand") or tags.get("operator") or "Unnamed EV charging station")
    elif amenity in ("restaurant", "fast_food", "cafe", "food_court"):
        extra["kind"] = amenity
        if tags.get("cuisine"):
            extra["cuisine"] = tags["cuisine"].replace(";", ", ").replace("_", " ")
        generic = {"restaurant": "Unnamed restaurant", "fast_food": "Unnamed fast-food outlet",
                   "cafe": "Unnamed café", "food_court": "Unnamed food court"}[amenity]
        rec.update(category="restaurant", name=name or generic)
    elif amenity == "parking":
        if tags.get("parking") in ("street_side", "lane"):
            return None
        extra["fee"] = tags.get("fee")
        rec.update(category="parking", name=name or "Parking area")
    elif amenity == "toilets":
        extra["fee"] = tags.get("fee")
        rec.update(category="restroom", name=name or "Public toilet")
    else:
        return None
    rec["name"] = rec["name"][:200]
    rec["extra"] = {k: v for k, v in extra.items() if v is not None}
    return rec


def normalise_ocm(item: dict) -> Optional[dict]:
    info = item.get("AddressInfo") or {}
    lat, lon = info.get("Latitude"), info.get("Longitude")
    if lat is None or lon is None or not in_india(float(lat), float(lon)):
        return None
    connectors, power = [], None
    for conn in item.get("Connections") or []:
        title = ((conn.get("ConnectionType") or {}).get("Title") or "").strip()
        if title and title not in connectors:
            connectors.append(title)
        if conn.get("PowerKW"):
            power = max(power or 0.0, float(conn["PowerKW"]))
    status = (item.get("StatusType") or {})
    if status.get("IsOperational") is False:
        return None
    addr = ", ".join(x for x in [info.get("AddressLine1"), info.get("Town"), info.get("StateOrProvince")] if x)
    extra = {"website": info.get("RelatedURL"), "phone": info.get("ContactTelephone1"),
             "operator": (item.get("OperatorInfo") or {}).get("Title"),
             "ocm_url": f"https://map.openchargemap.io/?id={item.get('ID')}", "car_compatible": True}
    return {"external_id": f"ocm:{item.get('ID')}", "name": (info.get("Title") or "Unnamed EV charging station")[:200],
            "category": "ev", "latitude": float(lat), "longitude": float(lon), "address": addr[:400],
            "fuel_types": None, "connector_types": connectors, "charging_power_kw": power,
            "num_chargers": item.get("NumberOfPoints"), "source": "ocm",
            "extra": {k: v for k, v in extra.items() if v}}


# ─── Storage ──────────────────────────────────────────────────────────────────

_UPSERT_COLUMNS = ("name", "category", "latitude", "longitude", "address", "fuel_types", "connector_types",
                   "charging_power_kw", "num_chargers", "source", "extra", "last_updated", "is_operational")


def store_section(section_key: str, provider: str, items: List[dict], status: str, message: str = "") -> None:
    """Upsert facilities (ON CONFLICT on external_id) and record the fetch. Runs in a worker thread."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        unique = {it["external_id"]: it for it in items}
        rows = [dict(it, last_updated=now, created_at=now, is_operational=True)
                for _, it in sorted(unique.items())]
        for i in range(0, len(rows), 500):
            stmt = pg_insert(Facility).values(rows[i:i + 500])
            stmt = stmt.on_conflict_do_update(
                index_elements=["external_id"],
                set_={c: getattr(stmt.excluded, c) for c in _UPSERT_COLUMNS})
            db.execute(stmt)
        db.add(FacilityFetch(section_key=section_key, provider=provider, status=status,
                             item_count=len(rows), message=(message or "")[:300], fetched_at=now))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Storing %s facilities for section %s failed: %s", provider, section_key, e)
    finally:
        db.close()


# ─── Fetching ─────────────────────────────────────────────────────────────────

def _section_key(points: Sequence[Tuple[float, float]]) -> str:
    raw = json.dumps([[round(a, 2), round(b, 2)] for a, b in points]
                     + [settings.FUEL_CORRIDOR_KM, settings.AMENITY_CORRIDOR_KM, QUERY_VERSION])
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def _overpass_query(points: Sequence[Tuple[float, float]]) -> str:
    pts = ",".join(f"{a:.5f},{b:.5f}" for a, b in points)
    return _OVERPASS_QUERY.format(timeout=settings.OVERPASS_QUERY_TIMEOUT, pts=pts,
                                  fuel_m=int(settings.FUEL_CORRIDOR_KM * 1000),
                                  amen_m=int(settings.AMENITY_CORRIDOR_KM * 1000))


async def _fetch_osm_section(key: str, points: List[Tuple[float, float]], mirror_offset: int) -> None:
    urls = settings.overpass_urls
    query = _overpass_query(points)
    last = "no Overpass server configured"
    for attempt in range(max(1, settings.OVERPASS_ATTEMPTS)):
        if not urls:
            break
        url = urls[(mirror_offset + attempt) % len(urls)]
        try:
            async with _semaphore():
                async with httpx.AsyncClient(
                        timeout=httpx.Timeout(settings.OVERPASS_HTTP_TIMEOUT, connect=settings.OVERPASS_CONNECT_TIMEOUT),
                        headers={"User-Agent": settings.HTTP_USER_AGENT}) as client:
                    resp = await client.post(url, data={"data": query})
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            data = resp.json()
            remark = (data.get("remark") or "").lower()
            items = [r for r in (normalise_osm(e) for e in data.get("elements", [])) if r]
            if "runtime error" in remark or "timed out" in remark:
                # Partial answer: keep what we got but do not cache the section as complete.
                await asyncio.to_thread(store_section, key, "osm", items, "failed", "partial: " + remark[:200])
                last = "server returned a partial result"
                continue
            await asyncio.to_thread(store_section, key, "osm", items, "ok")
            logger.info("Overpass section %s: %d facilities from %s", key[:8], len(items), url)
            return
        except Exception as e:
            last = f"{type(e).__name__}: {e}"[:200]
            logger.warning("Overpass section %s attempt %d via %s failed: %s", key[:8], attempt + 1, url, last)
            await asyncio.sleep(1.0 + attempt)
    await asyncio.to_thread(store_section, key, "osm", [], "failed", last)


async def _fetch_ocm_section(key: str, points: List[Tuple[float, float]]) -> None:
    mid = points[len(points) // 2]
    radius = max(haversine_km(mid[0], mid[1], p[0], p[1]) for p in points) + settings.FUEL_CORRIDOR_KM
    params = {"output": "json", "countrycode": "IN", "latitude": mid[0], "longitude": mid[1],
              "distance": int(math.ceil(radius)), "distanceunit": "KM", "maxresults": 500,
              "compact": "true", "verbose": "false", "key": settings.OPENCHARGEMAP_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.OCM_TIMEOUT, connect=5.0),
                                     headers={"User-Agent": settings.HTTP_USER_AGENT}) as client:
            resp = await client.get(settings.OPENCHARGEMAP_URL, params=params)
        resp.raise_for_status()
        items = [r for r in (normalise_ocm(i) for i in resp.json()) if r]
        await asyncio.to_thread(store_section, key, "ocm", items, "ok")
    except Exception as e:
        logger.warning("Open Charge Map section %s failed: %s", key[:8], type(e).__name__)
        await asyncio.to_thread(store_section, key, "ocm", [], "failed", type(e).__name__)


def _latest_fetches(db: Session, keys: Iterable[str], provider: str) -> Dict[str, FacilityFetch]:
    rows = (db.query(FacilityFetch)
            .filter(FacilityFetch.section_key.in_(list(keys)), FacilityFetch.provider == provider)
            .order_by(FacilityFetch.fetched_at.asc()).all())
    latest: Dict[str, FacilityFetch] = {}
    for r in rows:
        latest[r.section_key] = r
    return latest


async def ensure_corridor_data(db: Session, coords: List[Tuple[float, float]], total_km: float,
                               wait_seconds: float) -> dict:
    """Start (or reuse) background fetches for every route section that is not
    cached, wait up to `wait_seconds`, and report coverage."""
    cum = cumulative_km(coords)
    scale = total_km / cum[-1] if cum[-1] > 0 else 1.0
    sections = split_sections(coords, cum, settings.SECTION_KM)
    keyed = []
    for s in sections:
        pts = sample_along(s.points, cumulative_km(s.points), settings.SECTION_SAMPLE_KM)
        keyed.append((s, _section_key(pts), pts))

    providers = ["osm"] + (["ocm"] if settings.OPENCHARGEMAP_API_KEY else [])
    if not settings.USE_EXTERNAL_FACILITIES:
        return {"sections_total": len(sections), "sections_ready": 0, "sections_failed": 0,
                "sections_pending": 0, "complete": True, "external_enabled": False, "failed_ranges_km": []}

    fresh_after = datetime.utcnow() - timedelta(days=settings.FACILITY_CACHE_DAYS)
    retry_after = datetime.utcnow() - timedelta(seconds=60)
    latest = {p: _latest_fetches(db, [k for _, k, _ in keyed], p) for p in providers}
    tasks = []
    for idx, (s, key, pts) in enumerate(keyed):
        for p in providers:
            last = latest[p].get(key)
            if last and last.status == "ok" and last.fetched_at >= fresh_after:
                continue
            if last and last.status == "failed" and last.fetched_at >= retry_after:
                continue           # failed moments ago - don't hammer the servers
            tkey = f"{p}:{key}"
            task = _inflight.get(tkey)
            if task is None or task.done():
                coro = _fetch_osm_section(key, pts, idx) if p == "osm" else _fetch_ocm_section(key, pts)
                task = asyncio.create_task(coro)
                _inflight[tkey] = task
                task.add_done_callback(lambda t, k=tkey: _inflight.pop(k, None) if _inflight.get(k) is t else None)
            tasks.append(task)

    if tasks and wait_seconds > 0:
        await asyncio.wait(tasks, timeout=wait_seconds)   # never cancels: unfinished fetches keep running

    db.expire_all()
    latest_osm = _latest_fetches(db, [k for _, k, _ in keyed], "osm")
    ready = failed = pending = 0
    failed_ranges, stale = [], 0
    for s, key, _ in keyed:
        last = latest_osm.get(key)
        if f"osm:{key}" in _inflight:
            pending += 1
        elif last and last.status == "ok":
            ready += 1
            if last.fetched_at < fresh_after:
                stale += 1
        else:
            failed += 1
            failed_ranges.append([round(s.start_km * scale), round(s.end_km * scale)])
    return {"sections_total": len(keyed), "sections_ready": ready, "sections_failed": failed,
            "sections_pending": pending, "complete": pending == 0, "external_enabled": True,
            "failed_ranges_km": failed_ranges, "stale_sections": stale}


# ─── Querying the corridor ───────────────────────────────────────────────────

def _radius_for(category: str) -> float:
    return settings.FUEL_CORRIDOR_KM if category in ("fuel", "ev") else settings.AMENITY_CORRIDOR_KM


def _info_score(f: dict) -> int:
    return (0 if f["name"].startswith("Unnamed") else 4) + len(f.get("extra") or {})


def _dedupe(items: List[dict]) -> List[dict]:
    """Remove the same physical place reported twice (node + area in OSM, or OSM + OCM)."""
    items = sorted(items, key=lambda f: -_info_score(f))
    kept: List[dict] = []
    grid: Dict[Tuple[str, int, int], List[dict]] = {}
    for f in items:
        cell = (f["category"], int(f["latitude"] * 500), int(f["longitude"] * 500))   # ~220 m cells
        radius_m = 150 if f["category"] == "ev" else 75
        dup = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for g in grid.get((cell[0], cell[1] + dy, cell[2] + dx), ()):
                    if haversine_km(f["latitude"], f["longitude"], g["latitude"], g["longitude"]) * 1000 <= radius_m:
                        same_name = f["name"] == g["name"] or f["name"].startswith("Unnamed") or g["name"].startswith("Unnamed")
                        if same_name or f["source"] != g["source"]:
                            dup = True
                            break
                if dup:
                    break
            if dup:
                break
        if not dup:
            kept.append(f)
            grid.setdefault(cell, []).append(f)
    return kept


def _rank_and_cap(items: List[dict], cap: int) -> List[dict]:
    """Keep the most useful facilities, spread along the whole route:
    within each 10 km stretch prefer small detours and named/well-described places."""
    if len(items) <= cap:
        return items
    buckets: Dict[int, List[dict]] = {}
    for f in items:
        buckets.setdefault(int(f["km_along"] // 10), []).append(f)
    for b in buckets.values():
        b.sort(key=lambda f: (f["detour_km"], -_info_score(f)))
    chosen, depth = [], 0
    while len(chosen) < cap:
        added = False
        for k in sorted(buckets):
            if depth < len(buckets[k]):
                chosen.append(buckets[k][depth])
                added = True
                if len(chosen) >= cap:
                    break
        if not added:
            break
        depth += 1
    return chosen


def corridor_facilities(db: Session, coords: List[Tuple[float, float]], total_km: float,
                        categories: Optional[Sequence[str]] = None, cap: Optional[int] = None) -> List[dict]:
    """Facilities within the corridor, with km_along / distance off route / detour."""
    cats = set(categories or CATEGORIES)
    db_cats = {"fuel" if c == "cng" else c for c in cats}
    projector = RouteProjector(coords, total_km)
    cum = cumulative_km(coords)
    boxes = []
    for s in split_sections(coords, cum, 50.0):
        mn_lat, mn_lon, mx_lat, mx_lon = bounding_box(s.points, settings.FUEL_CORRIDOR_KM + 0.5)
        boxes.append(and_(Facility.latitude.between(mn_lat, mx_lat), Facility.longitude.between(mn_lon, mx_lon)))
    rows = (db.query(Facility)
            .filter(Facility.is_operational.is_(True), Facility.category.in_(db_cats), or_(*boxes))
            .all())

    out = []
    for fac in rows:
        radius = _radius_for(fac.category)
        km_along, off = projector.project(fac.latitude, fac.longitude, max_off_km=radius + 0.5)
        if off > radius:
            continue
        fuel_types = fac.fuel_types or []
        if fac.category == "fuel" and "fuel" not in cats and "cng" not in fuel_types:
            continue          # only CNG was requested
        detour = 0.0 if off < 0.15 else 2 * off * settings.ROAD_FACTOR
        extra = fac.extra or {}
        out.append({
            "id": fac.id, "name": fac.name, "category": fac.category,
            "latitude": fac.latitude, "longitude": fac.longitude, "address": fac.address or "",
            "fuel_types": fuel_types, "fuel_types_inferred": bool(extra.get("fuel_types_inferred")),
            "connector_types": fac.connector_types or [], "charging_power_kw": fac.charging_power_kw,
            "num_chargers": fac.num_chargers,
            "km_along": round(min(max(km_along, 0.0), total_km), 1),
            "distance_from_route_km": round(off, 2),
            "detour_km": round(detour, 1),
            "detour_min": int(round(detour / settings.DETOUR_SPEED_KMH * 60)),
            "source": fac.source, "source_label": SOURCE_LABEL.get(fac.source, fac.source),
            "extra": extra,
            "last_updated": fac.last_updated.isoformat() if fac.last_updated else None,
        })
    out = _dedupe(out)
    if cap:
        groups: Dict[str, List[dict]] = {}
        for f in out:
            groups.setdefault(f["category"], []).append(f)
        out = [f for g in groups.values() for f in _rank_and_cap(g, cap)]
    out.sort(key=lambda f: (f["km_along"], f["detour_km"]))
    return out


def count_by_category(items: List[dict]) -> Dict[str, int]:
    counts = {c: 0 for c in CATEGORIES}
    for f in items:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
        if f["category"] == "fuel" and "cng" in (f.get("fuel_types") or []):
            counts["cng"] += 1
    return counts


def coverage_warnings(coverage: dict, total_found: int) -> List[str]:
    w = []
    if not coverage.get("external_enabled", True):
        w.append("Live facility lookup is turned off (USE_EXTERNAL_FACILITIES=false); only previously cached "
                 "OpenStreetMap data is shown.")
    if coverage.get("sections_pending"):
        w.append(f"Still loading facility data for {coverage['sections_pending']} of "
                 f"{coverage['sections_total']} route sections…")
    if coverage.get("sections_failed"):
        ranges = ", ".join(f"km {a}–{b}" for a, b in coverage["failed_ranges_km"][:6])
        w.append(f"OpenStreetMap data could not be loaded for {coverage['sections_failed']} of "
                 f"{coverage['sections_total']} route sections ({ranges}). Facilities there may be missing.")
    if coverage.get("stale_sections"):
        w.append(f"{coverage['stale_sections']} route sections use cached data older than "
                 f"{settings.FACILITY_CACHE_DAYS} days.")
    if total_found == 0 and coverage.get("complete"):
        w.append("No verified facility found in this corridor.")
    return w


async def get_corridor(db: Session, coords: List[Tuple[float, float]], total_km: float, wait_seconds: float,
                       categories: Optional[Sequence[str]] = None, cap: Optional[int] = None) -> dict:
    """Main entry point used by the API and the optimiser. Never raises for provider failures."""
    try:
        coverage = await ensure_corridor_data(db, coords, total_km, wait_seconds)
    except Exception as e:
        logger.exception("Facility discovery failed: %s", e)
        coverage = {"sections_total": 0, "sections_ready": 0, "sections_failed": 0, "sections_pending": 0,
                    "complete": True, "external_enabled": True, "failed_ranges_km": [],
                    "error": "Facility discovery is temporarily unavailable."}
    items = corridor_facilities(db, coords, total_km, categories, cap)
    sources: Dict[str, int] = {}
    for f in items:
        sources[f["source_label"]] = sources.get(f["source_label"], 0) + 1
    warnings = coverage_warnings(coverage, len(items))
    if coverage.get("error"):
        warnings.insert(0, coverage["error"])
    return {"facilities": items, "counts": count_by_category(items), "coverage": coverage,
            "sources": sources, "warnings": warnings}
