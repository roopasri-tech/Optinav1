"""OSM tag interpretation, de-duplication and route geometry helpers.
Elements below are hand-written TEST inputs in Overpass JSON format."""
import pytest

from app.services.facility_service import _dedupe, _overpass_query, detect_fuel_types, normalise_osm
from app.utils.geo import RouteProjector, cumulative_km, split_sections


def test_cng_tag_no_is_not_cng():
    fuels, inferred = detect_fuel_types({"amenity": "fuel", "fuel:cng": "no", "fuel:petrol": "yes"})
    assert "cng" not in fuels and fuels == ["petrol"] and not inferred


def test_cng_from_tag_and_name():
    assert "cng" in detect_fuel_types({"fuel:cng": "yes"})[0]
    assert detect_fuel_types({"name": "Sai CNG Station"})[0] == ["cng"]


def test_untagged_station_is_inferred_petrol_diesel():
    fuels, inferred = detect_fuel_types({"amenity": "fuel", "name": "Sri Fuels"})
    assert fuels == ["petrol", "diesel"] and inferred


def test_oil_company_brand_with_cng_keeps_petrol():
    fuels, inferred = detect_fuel_types({"brand": "Indian Oil", "fuel:cng": "yes"})
    assert set(fuels) == {"petrol", "diesel", "cng"} and inferred


def test_normalise_node_and_way_center():
    node = normalise_osm({"type": "node", "id": 1, "lat": 17.4, "lon": 78.5,
                          "tags": {"amenity": "restaurant", "name": "Test Dhaba", "cuisine": "indian"}})
    way = normalise_osm({"type": "way", "id": 2, "center": {"lat": 17.41, "lon": 78.51},
                         "tags": {"amenity": "parking"}})
    assert node["category"] == "restaurant" and node["external_id"] == "osm:node/1"
    assert way["category"] == "parking" and way["latitude"] == 17.41 and way["name"] == "Parking area"


def test_unnamed_places_are_not_given_invented_names():
    f = normalise_osm({"type": "node", "id": 3, "lat": 17.4, "lon": 78.5, "tags": {"amenity": "fast_food"}})
    assert f["name"] == "Unnamed fast-food outlet"


def test_private_and_foreign_elements_skipped():
    assert normalise_osm({"type": "node", "id": 4, "lat": 17.4, "lon": 78.5,
                          "tags": {"amenity": "parking", "access": "private"}}) is None
    assert normalise_osm({"type": "node", "id": 5, "lat": 48.8, "lon": 2.3,
                          "tags": {"amenity": "fuel"}}) is None
    assert normalise_osm({"type": "node", "id": 6, "tags": {"amenity": "fuel"}}) is None


def test_ev_power_and_connectors():
    f = normalise_osm({"type": "node", "id": 7, "lat": 17.4, "lon": 78.5,
                       "tags": {"amenity": "charging_station", "socket:type2_combo": "2",
                                "socket:type2_combo:output": "60 kW", "socket:type2": "1"}})
    assert f["category"] == "ev" and f["charging_power_kw"] == 60 and "CCS2" in f["connector_types"]


def test_overpass_query_has_coordinates_output():
    q = _overpass_query([(17.0, 78.0), (17.1, 78.1)])
    assert "out center;" in q and "out center tags" not in q    # 'tags' would drop node coordinates
    assert "around:5000,17.00000,78.00000,17.10000,78.10000" in q


def _f(i, cat, lat, lon, name, src="osm"):
    return {"id": i, "category": cat, "latitude": lat, "longitude": lon, "name": name, "source": src, "extra": {}}


def test_dedupe_node_and_area_of_same_pump():
    items = [_f(1, "fuel", 17.0, 78.0, "HP Pump"), _f(2, "fuel", 17.0002, 78.0, "HP Pump"),
             _f(3, "fuel", 17.01, 78.0, "Other Pump"), _f(4, "restaurant", 17.0, 78.0, "HP Pump")]
    kept = _dedupe(items)
    assert {f["id"] for f in kept} in ({1, 3, 4}, {2, 3, 4})


def test_dedupe_osm_and_ocm_charger():
    items = [_f(1, "ev", 17.0, 78.0, "Charger A"), _f(2, "ev", 17.0008, 78.0, "Charger A (OCM)", "ocm")]
    assert len(_dedupe(items)) == 1


def test_projection_and_sections():
    line = [(17.0, 78.0 + i * 0.01) for i in range(101)]     # ~106 km due east
    cum = cumulative_km(line)
    proj = RouteProjector(line, total_km=cum[-1])
    km, off = proj.project(17.02, 78.5)                       # ~2.2 km north of the middle
    assert km == pytest.approx(cum[-1] / 2, rel=0.01)
    assert off == pytest.approx(2.21, abs=0.05)
    secs = split_sections(line, cum, 30.0)
    assert len(secs) == 4 and secs[0].start_km == 0 and secs[-1].end_km == pytest.approx(cum[-1])
