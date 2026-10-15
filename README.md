# SmartRoute — Intelligent Multi-Fuel Trip Cost & Stop Optimisation

India-wide road-trip planner for **petrol, diesel, CNG, bi-fuel (CNG + petrol) and EV** vehicles:
real road route, realistic usable range, required refuelling/charging stops, consumption-based
cost, and real facilities (fuel, CNG, EV chargers, food, parking, restrooms) along the route.

## Run it

Requirements: Docker Desktop (with Docker Compose) and an internet connection.

```bash
docker compose up --build
```

| What | URL |
|---|---|
| App | http://localhost:8080 |
| API (Swagger) | http://localhost:8000/docs |

First start takes a few minutes (images are built, database migrated, sample vehicles seeded).
Stop with `Ctrl+C`; `docker compose down` removes the containers (data stays in the `pg_data`
volume; `docker compose down -v` wipes it).

Optional: copy `.env.example` to `.env` to add a free Open Charge Map API key or change default fuel prices.

## How it works

**Route** — the start/destination you pick in the autocomplete (Photon, OpenStreetMap data) are used
with their exact coordinates. The road route, distance and driving time come from OSRM
(`router.project-osrm.org`, falling back to `routing.openstreetmap.de`). If both are down the app says
so — it never shows a straight-line estimate as a road distance.

**Range** — for every fuel/battery:
`usable range = capacity × current level × efficiency × safety factor (0.85)`.
A bi-fuel car has two separate tanks; it burns the cheaper fuel (CNG) first, then petrol.

**Stops** — if the trip is longer than the usable range, stops are required. The planner checks
every leg against the conservative range (including detours to the station), refills to 100 %
(EVs charge to 80 %), and among all feasible plans picks the lowest-cost one (or the fewest-stops
one — the user chooses; the other is shown for comparison). At the last stop it only buys what is
needed to reach the destination with the safety margin.

**Cost** — `fuel needed = distance ÷ efficiency`, `cost = fuel needed × price`, per fuel, using rated
efficiency (the 15 % safety margin is used only for feasibility). "Pay at stops" is shown separately.
Savings = baseline − plan cost, where the baseline is "same distance on petrol" for bi-fuel cars
and "naive refuelling" for single-fuel vehicles (for which savings are usually ~₹0 — and the UI says so).
If no feasible plan exists the app explains why — it never shows ₹0 or fake savings.

**Facilities** — fetched from OpenStreetMap (Overpass API) along the actual route corridor
(5 km for fuel/EV, 2 km for food/parking/toilets), in ~150 km sections, two at a time, rotating across
three Overpass mirrors with retries. Results are cached in PostgreSQL for 7 days, de-duplicated,
positioned along the route (km, distance off route, approximate detour) and ranked. Requests never
wait more than ~20 s; remaining sections keep loading in the background and the page updates itself.
EV chargers are also taken from Open Charge Map when an API key is configured. No facilities are
invented: unnamed places are shown as "Unnamed …", and stations whose fuel types are not tagged in
OpenStreetMap are flagged as "assumed".

## Tests

```bash
docker compose exec backend python -m pytest -q
```

Unit tests cover range/stop/cost maths, OSM tag parsing, de-duplication and geometry; API tests run
against the real database with routing/facility providers replaced by test fakes.

## Project layout

```
backend/   FastAPI, SQLAlchemy, Alembic migrations, optimiser (app/optimization), services, tests
frontend/  React + TypeScript + Vite + Tailwind + Leaflet, served by nginx (proxies /api)
docker-compose.yml   db (PostgreSQL/PostGIS) + backend + frontend
```

Map data © OpenStreetMap contributors (ODbL). Routing by OSRM. Place search by Photon (komoot).
