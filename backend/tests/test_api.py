"""API tests against a real PostgreSQL database (DATABASE_URL). External providers
are replaced by in-test fakes; facilities are TEST records stored for one test route.
Skipped automatically when no database is reachable."""
import pytest
from sqlalchemy import text

from app.config.settings import settings
from app.database.session import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("SELECT 1 FROM vehicles LIMIT 1"))
    DB_OK = True
except Exception:
    DB_OK = False

pytestmark = pytest.mark.skipif(not DB_OK, reason="database not reachable / not migrated")

if DB_OK:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import facility_service, route_service

    client = TestClient(app)


# A straight 700 km test road heading north from (15.0, 78.0).
LINE = [[15.0 + i * 0.0315, 78.0] for i in range(201)]


@pytest.fixture(autouse=True, scope="module")
def cleanup_test_records():
    yield
    with SessionLocal() as db:   # remove everything these tests created
        db.execute(text("DELETE FROM routes WHERE source_name = 'Test A'"))
        db.execute(text("UPDATE trip_stops SET facility_id = NULL WHERE facility_id IN "
                        "(SELECT id FROM facilities WHERE external_id LIKE 'osm:node/9900%')"))
        db.execute(text("DELETE FROM facilities WHERE external_id LIKE 'osm:node/9900%'"))
        db.execute(text("DELETE FROM facility_fetches WHERE section_key = 'test-section'"))
        db.commit()


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    async def fake_get_route(s_lat, s_lon, d_lat, d_lon):
        return {"distance_km": 700.0, "duration_min": 724, "geometry": LINE, "provider": "osrm"}

    monkeypatch.setattr(route_service, "get_route", fake_get_route)
    monkeypatch.setattr(settings, "USE_EXTERNAL_FACILITIES", False)


def _store_test_facilities():
    items = []
    for i in range(1, 7):     # TEST fuel stations every ~100 km, 1 km off the road
        items.append({"external_id": f"osm:node/990000{i}", "name": f"TEST pump {i}", "category": "fuel",
                      "latitude": 15.0 + i * 0.9, "longitude": 78.0095, "address": "",
                      "fuel_types": ["petrol", "diesel"], "connector_types": None, "charging_power_kw": None,
                      "num_chargers": None, "source": "osm", "extra": {}})
    items.append({"external_id": "osm:node/9900100", "name": "TEST dhaba", "category": "restaurant",
                  "latitude": 16.0, "longitude": 78.005, "address": "", "fuel_types": None,
                  "connector_types": None, "charging_power_kw": None, "num_chargers": None,
                  "source": "osm", "extra": {}})
    facility_service.store_section("test-section", "osm", items, "ok")


def _route():
    r = client.post("/api/routes/plan", json={"source": {"query": "Test A", "lat": 15.0, "lon": 78.0},
                                              "destination": {"query": "Test B", "lat": 21.3, "lon": 78.0}})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_lists():
    assert client.get("/api/health").json()["database"] == "ok"
    assert isinstance(client.get("/api/vehicles").json(), list)
    for path in ("/api/stations", "/api/chargers", "/api/restaurants", "/api/amenities"):
        assert client.get(path).status_code == 200


def test_route_plan_keeps_selected_destination():
    route = _route()
    assert route["destination"]["label"] == "Test B"
    assert route["destination"]["lat"] == 21.3
    assert route["distance_km"] == 700.0 and route["duration_min"] == 724


def test_invalid_inputs_are_rejected():
    assert client.post("/api/routes/plan", json={"source": {"query": ""}, "destination": {"query": "x"}}).status_code == 422
    r = client.post("/api/routes/plan", json={"source": {"query": "Paris", "lat": 48.85, "lon": 2.35},
                                              "destination": {"query": "B", "lat": 21.3, "lon": 78.0}})
    assert r.status_code == 400 and "outside India" in r.json()["detail"]
    assert client.post("/api/optimization/trip", json={"vehicle_id": 999999, "route_id": 1}).status_code in (404, 422)
    assert client.post("/api/vehicles", json={"name": "Bad", "fuel_type": "petrol", "tank_capacity": -5}).status_code == 422
    assert client.post("/api/vehicles", json={"name": "Bad EV", "fuel_type": "electric"}).status_code == 400
    assert client.get("/api/places/near-route", params={"route_id": 1, "category": "bogus"}).status_code == 400


def test_near_route_and_optimisation():
    _store_test_facilities()
    route = _route()
    near = client.post("/api/places/near-route", json={"route_id": route["id"]}).json()
    assert near["counts"]["fuel"] >= 6 and near["counts"]["restaurant"] >= 1
    assert all(0 <= f["km_along"] <= 700 for f in near["facilities"])
    pump = next(f for f in near["facilities"] if f["name"] == "TEST pump 1")
    assert pump["distance_from_route_km"] == pytest.approx(1.0, abs=0.1)
    assert pump["detour_km"] == pytest.approx(2 * 1.0 * settings.ROAD_FACTOR, abs=0.2)

    vid = client.post("/api/vehicles", json={"name": "TEST car", "fuel_type": "petrol", "tank_capacity": 30,
                                             "efficiency": 12, "current_fuel_pct": 50}).json()["id"]
    try:
        r = client.post("/api/optimization/trip", json={"vehicle_id": vid, "route_id": route["id"]})
        assert r.status_code == 200, r.text
        res = r.json()
        opt = res["optimization"]
        assert res["range_check"]["usable_range_km"] == pytest.approx(30 * 0.5 * 12 * settings.SAFETY_FACTOR, abs=0.1)
        assert res["range_check"]["needs_stop"] is True
        assert opt["feasible"] is True and len(opt["stops"]) >= 2
        assert opt["energy_cost_inr"] == pytest.approx(opt["driven_km"] / 12 * settings.PETROL_PRICE, rel=1e-3)
        assert opt["savings_inr"] is None or opt["savings_inr"] < opt["baseline"]["cost_inr"]

        # 0 % fuel and no station before km 90 -> infeasible with an explanation, never Rs 0
        r = client.post("/api/optimization/trip", json={"vehicle_id": vid, "route_id": route["id"],
                                                        "current_fuel_pct": 0})
        opt = r.json()["optimization"]
        assert opt["feasible"] is False and opt["energy_cost_inr"] is None and opt["stops"] == []
        assert "safe range" in opt["message"]
        trip = client.get(f"/api/trips/{r.json()['trip_id']}").json()
        assert trip["optimization"]["feasible"] is False
    finally:
        assert client.delete(f"/api/vehicles/{vid}").status_code == 204
