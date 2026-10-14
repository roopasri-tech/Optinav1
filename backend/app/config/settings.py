from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunables come from environment variables (or backend/.env). No secrets in code."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://smartroute:smartroute@db:5432/smartroute"

    # ── External providers ────────────────────────────────────────────────────
    # Road routing (OSRM HTTP API). The second server is tried if the first fails.
    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    OSRM_FALLBACK_URL: str = "https://routing.openstreetmap.de/routed-car"
    OSRM_TIMEOUT: float = 20.0

    # Place search (autocomplete). Photon is built for type-ahead search;
    # Nominatim's usage policy forbids autocomplete, so it is only used for
    # one-off lookups when Photon fails.
    PHOTON_URL: str = "https://photon.komoot.io/api/"
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org/search"
    GEOCODER_TIMEOUT: float = 8.0

    # OpenStreetMap Overpass mirrors, comma-separated. Route sections are spread
    # across mirrors and a failed section is retried on the next mirror.
    OVERPASS_URLS: str = (
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter"
    )
    OPENCHARGEMAP_API_KEY: str = ""     # optional; free key from openchargemap.org
    OPENCHARGEMAP_URL: str = "https://api.openchargemap.io/v3/poi/"
    HTTP_USER_AGENT: str = "SmartRoute/1.0 (B.Tech trip-planner project)"

    # ── Facility discovery ────────────────────────────────────────────────────
    USE_EXTERNAL_FACILITIES: bool = True
    FUEL_CORRIDOR_KM: float = 5.0        # fuel / CNG / EV search radius around the route
    AMENITY_CORRIDOR_KM: float = 2.0     # restaurants / parking / restrooms radius
    SECTION_KM: float = 150.0            # route is split into sections of this length
    SECTION_SAMPLE_KM: float = 3.0       # polyline sampling step inside a section query
    OVERPASS_QUERY_TIMEOUT: int = 25     # server-side [timeout:..] in seconds
    OVERPASS_HTTP_TIMEOUT: float = 30.0  # client-side read timeout per request
    OVERPASS_CONNECT_TIMEOUT: float = 5.0
    OVERPASS_CONCURRENCY: int = 2        # public servers allow ~2 slots per IP
    OVERPASS_ATTEMPTS: int = 3           # each attempt uses the next mirror
    OCM_TIMEOUT: float = 10.0
    NEAR_ROUTE_WAIT_SECONDS: float = 20.0   # max wait inside /places/near-route
    OPTIMIZE_WAIT_SECONDS: float = 45.0     # max wait for fuel data inside optimisation
    FACILITY_CACHE_DAYS: int = 7         # a fetched route section is re-used for this long
    MAX_FACILITIES_PER_CATEGORY: int = 250

    # ── Range / optimisation ──────────────────────────────────────────────────
    # usable_range = capacity x level x efficiency x SAFETY_FACTOR
    SAFETY_FACTOR: float = 0.85
    ROAD_FACTOR: float = 1.3             # straight-line -> road distance for short detours
    DETOUR_SPEED_KMH: float = 30.0
    STOP_TIME_MIN: float = 10.0          # time spent per fuel stop
    TIME_VALUE_INR_PER_MIN: float = 2.0  # used only to rank plans, never reported as cost
    EV_MAX_CHARGE_PCT: float = 80.0      # DC fast charging normally stops at ~80 %
    EV_DEFAULT_POWER_KW: float = 30.0    # assumed when a charger's power is unknown
    EV_CHARGE_EFFICIENCY: float = 0.9

    # Default prices (INR). Approximate national averages - the user can override per trip.
    PETROL_PRICE: float = 102.0
    DIESEL_PRICE: float = 90.0
    CNG_PRICE: float = 89.0          # per kg
    ELECTRICITY_PRICE: float = 18.0  # per kWh at public DC chargers

    CORS_ORIGINS: List[str] = ["http://localhost:8080", "http://localhost:3000", "http://localhost:5173"]

    @property
    def overpass_urls(self) -> List[str]:
        return [u.strip() for u in self.OVERPASS_URLS.split(",") if u.strip()]


settings = Settings()
