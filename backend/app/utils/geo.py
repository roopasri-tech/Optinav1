"""Geographic helpers: distances, polyline simplification, route sections and
fast projection of points onto a route ("how far along, how far off")."""
import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

LatLon = Tuple[float, float]

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQ = 111.320

# Rough bounding box of India (used to reject obviously wrong coordinates).
INDIA_BOUNDS = (6.0, 68.0, 37.6, 97.6)  # min_lat, min_lon, max_lat, max_lon


def in_india(lat: float, lon: float) -> bool:
    return INDIA_BOUNDS[0] <= lat <= INDIA_BOUNDS[2] and INDIA_BOUNDS[1] <= lon <= INDIA_BOUNDS[3]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return r * 2 * math.asin(min(1.0, math.sqrt(a)))


def cumulative_km(coords: Sequence[LatLon]) -> List[float]:
    """Running path length; cum[i] = km from coords[0] to coords[i] along the polyline."""
    cum = [0.0]
    for i in range(1, len(coords)):
        a, b = coords[i - 1], coords[i]
        cum.append(cum[-1] + haversine_km(a[0], a[1], b[0], b[1]))
    return cum


def decimate(coords: Sequence[LatLon], min_step_km: float = 0.4, max_points: int = 5000) -> List[LatLon]:
    """Drop points closer than min_step_km to the last kept point (keeps the shape of
    a road polyline while shrinking OSRM's very dense geometry). Always keeps both ends."""
    if len(coords) <= 2:
        return list(coords)
    kept = [coords[0]]
    for p in coords[1:-1]:
        last = kept[-1]
        if haversine_km(last[0], last[1], p[0], p[1]) >= min_step_km:
            kept.append(p)
    kept.append(coords[-1])
    if len(kept) > max_points:
        step = (len(kept) - 1) / (max_points - 1)
        kept = [kept[round(i * step)] for i in range(max_points)]
    return kept


def sample_along(coords: Sequence[LatLon], cum: Sequence[float], step_km: float) -> List[LatLon]:
    """Points spaced ~step_km apart along the polyline (plus both ends)."""
    if not coords:
        return []
    out = [coords[0]]
    next_km = step_km
    for i in range(1, len(coords)):
        while cum[i] >= next_km:
            seg = cum[i] - cum[i - 1]
            t = 0.0 if seg <= 0 else (next_km - cum[i - 1]) / seg
            a, b = coords[i - 1], coords[i]
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
            next_km += step_km
    if out[-1] != tuple(coords[-1]):
        out.append(tuple(coords[-1]))
    return out


@dataclass
class RouteSection:
    index: int
    start_km: float
    end_km: float
    points: List[LatLon]   # the part of the route polyline covering this section


def split_sections(coords: Sequence[LatLon], cum: Sequence[float], section_km: float) -> List[RouteSection]:
    """Split a route into consecutive sections of ~section_km path length."""
    total = cum[-1] if cum else 0.0
    if total <= 0 or len(coords) < 2:
        return [RouteSection(0, 0.0, total, list(coords))]
    n = max(1, math.ceil(total / section_km))
    length = total / n
    sections: List[RouteSection] = []
    start_idx = 0
    for k in range(n):
        end_km = total if k == n - 1 else (k + 1) * length
        end_idx = start_idx
        while end_idx < len(coords) - 1 and cum[end_idx] < end_km:
            end_idx += 1
        pts = list(coords[start_idx:end_idx + 1])
        if len(pts) < 2:
            pts = [coords[max(0, end_idx - 1)], coords[end_idx]]
        sections.append(RouteSection(k, cum[start_idx], cum[end_idx], pts))
        start_idx = end_idx
    return sections


def bounding_box(coords: Sequence[LatLon], padding_km: float = 5.0) -> Tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon) padded by padding_km."""
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    mid = (min(lats) + max(lats)) / 2
    pad_lat = padding_km / KM_PER_DEG_LAT
    pad_lon = padding_km / (KM_PER_DEG_LON_EQ * max(0.2, math.cos(math.radians(mid))))
    return min(lats) - pad_lat, min(lons) - pad_lon, max(lats) + pad_lat, max(lons) + pad_lon


class RouteProjector:
    """Projects points onto a route polyline.

    project(lat, lon) -> (km_along_route, perpendicular_distance_km)

    Segments are bucketed into a ~11 km grid so each lookup only examines the
    segments near the point instead of the whole route. Distances are computed in
    a local flat frame around the point, which is accurate to well under 1 % for
    the < 15 km offsets we care about.
    """

    CELL_DEG = 0.1

    def __init__(self, coords: Sequence[LatLon], total_km: float = None):
        self.coords = [tuple(c) for c in coords]
        self.cum = cumulative_km(self.coords)
        path_len = self.cum[-1] if self.cum else 0.0
        # Rescale so that km_along matches the routing provider's official distance.
        self.scale = (total_km / path_len) if (total_km and path_len > 0) else 1.0
        self.grid: Dict[Tuple[int, int], List[int]] = {}
        for i in range(len(self.coords) - 1):
            (la, loa), (lb, lob) = self.coords[i], self.coords[i + 1]
            for cy in range(self._cell(min(la, lb)), self._cell(max(la, lb)) + 1):
                for cx in range(self._cell(min(loa, lob)), self._cell(max(loa, lob)) + 1):
                    self.grid.setdefault((cy, cx), []).append(i)

    def _cell(self, deg: float) -> int:
        return int(math.floor(deg / self.CELL_DEG))

    def project(self, lat: float, lon: float, max_off_km: float = 12.0) -> Tuple[float, float]:
        cy, cx = self._cell(lat), self._cell(lon)
        candidates = set()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                candidates.update(self.grid.get((cy + dy, cx + dx), ()))
        if not candidates:
            return 0.0, float("inf")

        kx = KM_PER_DEG_LON_EQ * math.cos(math.radians(lat))
        ky = KM_PER_DEG_LAT
        best_d2, best_along = float("inf"), 0.0
        for i in candidates:
            (la, loa), (lb, lob) = self.coords[i], self.coords[i + 1]
            ax, ay = (loa - lon) * kx, (la - lat) * ky
            bx, by = (lob - lon) * kx, (lb - lat) * ky
            vx, vy = bx - ax, by - ay
            vv = vx * vx + vy * vy
            t = 0.0 if vv == 0 else max(0.0, min(1.0, -(ax * vx + ay * vy) / vv))
            px, py = ax + t * vx, ay + t * vy
            d2 = px * px + py * py
            if d2 < best_d2:
                best_d2 = d2
                best_along = self.cum[i] + t * (self.cum[i + 1] - self.cum[i])
        dist = math.sqrt(best_d2)
        if dist > max_off_km:
            return best_along * self.scale, float("inf")
        return best_along * self.scale, dist
