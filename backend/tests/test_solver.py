"""Unit tests for range, stop planning and cost maths.

The station layouts below are synthetic TEST FIXTURES (evenly spaced positions
along an abstract route) - they are not facility data used by the application.
"""
import time

import pytest

from app.config.settings import settings
from app.optimization.solver import naive_plan, plan_trip
from app.optimization.state import Candidate, FuelSpec, VehicleSpec

SF = settings.SAFETY_FACTOR


def wagonr(cng_pct=100.0, petrol_pct=80.0):
    # cheapest-per-km first: CNG 89/26 = 3.42 /km, petrol 102/14 = 7.29 /km
    return VehicleSpec(1, "Maruti WagonR CNG", "car", [
        FuelSpec("cng", 8.0, cng_pct, 26.0, 89.0),
        FuelSpec("petrol", 37.0, petrol_pct, 14.0, 102.0),
    ])


def creta(pct=100.0):
    return VehicleSpec(2, "Hyundai Creta", "car", [FuelSpec("petrol", 50.0, pct, 16.0, 102.0)])


def nexon(pct=90.0):
    return VehicleSpec(3, "Tata Nexon EV", "car",
                       [FuelSpec("electric", 40.5, pct, 6.5, 18.0, max_fill_pct=settings.EV_MAX_CHARGE_PCT)])


def stations(total_km, every_km, fuels, start_id=1, offset=7.0, detour=0.6, skip=None):
    out, km, i = [], offset, start_id
    while km < total_km - 1:
        if not (skip and skip[0] <= km <= skip[1]):
            out.append(Candidate(i, f"Test station {i}", 0.0, 0.0, km, detour, list(fuels)))
        km += every_km
        i += 1
    return out


def test_usable_range_formula():
    v = wagonr()
    cng, petrol = v.fuels
    assert cng.usable_range_km == pytest.approx(8.0 * 1.0 * 26.0 * SF)
    assert petrol.usable_range_km == pytest.approx(37.0 * 0.8 * 14.0 * SF)
    assert v.total_usable_range_km == pytest.approx(cng.usable_range_km + petrol.usable_range_km)


def test_short_trip_needs_no_stop_and_costs_real_money():
    v = creta()
    plan = plan_trip(300.0, v, stations(300, 25, ["petrol", "diesel"]))
    assert plan.feasible and plan.stops == []
    expected = 300.0 / 16.0 * 102.0          # fuel_needed x price
    assert plan.energy_cost_inr == pytest.approx(expected, rel=1e-3)
    assert plan.purchase_cost_inr == 0


def test_long_bifuel_trip_requires_stops_and_never_zero():
    """Hyderabad -> Jammu style: 2238 km with ~530 km usable range."""
    v = wagonr()
    total = 2238.0
    cands = stations(total, 30, ["petrol", "diesel"]) + stations(total, 95, ["cng", "petrol"], start_id=1000, offset=40)
    t0 = time.time()
    plan = plan_trip(total, v, cands)
    assert time.time() - t0 < 10
    assert plan.feasible
    assert v.total_usable_range_km < total
    assert len(plan.stops) >= 4
    assert plan.energy_cost_inr > 0 and plan.purchase_cost_inr > 0
    # consumption-based cost is bounded by all-CNG and all-petrol extremes
    assert total * (89 / 26) <= plan.energy_cost_inr <= plan.driven_km * (102 / 14) + 1
    assert sum(b["km"] for b in plan.fuel_breakdown.values()) == pytest.approx(plan.driven_km, abs=0.6)
    # it should use plenty of cheap CNG
    assert plan.fuel_breakdown["cng"]["km"] > 0.4 * total
    # every leg is within the safe range of a full refill of both tanks
    for leg in plan.legs:
        assert leg.distance_km <= sum(f.refill_range_km for f in v.fuels) + 1


def test_infeasible_gap_is_reported_not_zero():
    v = wagonr()
    total = 2238.0
    cands = stations(total, 30, ["petrol", "diesel", "cng"], skip=(400, 1600))
    plan = plan_trip(total, v, cands)
    assert not plan.feasible
    assert plan.energy_cost_inr == 0 and plan.stops == []
    assert 400 < plan.max_reachable_km < 1600


def test_no_stations_at_all_is_infeasible():
    plan = plan_trip(1500.0, creta(), [])
    assert not plan.feasible
    assert plan.max_reachable_km == pytest.approx(50 * 16 * SF, rel=0.01)


def test_petrol_trip_hyderabad_mumbai_one_stop():
    v = creta()
    total = 711.0
    plan = plan_trip(total, v, stations(total, 20, ["petrol", "diesel"]))
    assert plan.feasible and len(plan.stops) == 1
    assert plan.energy_cost_inr == pytest.approx(plan.driven_km / 16 * 102, rel=1e-3)
    # last stop buys only what is needed, not a full tank
    assert plan.stops[0].purchases[0].quantity < 50 * 0.6


def test_ev_trip_charges_to_80_percent():
    v = nexon()
    total = 570.0
    plan = plan_trip(total, v, stations(total, 45, ["electric"], detour=1.0))
    assert plan.feasible and len(plan.stops) >= 2
    for s in plan.stops[:-1]:
        assert s.purchases[0].level_after_pct == pytest.approx(80.0)
        assert s.purchases[0].charge_minutes > 0
    assert plan.energy_cost_inr == pytest.approx(plan.driven_km / 6.5 * 18.0, rel=1e-3)


def test_zero_percent_fuel_is_respected():
    v = creta(pct=0.0)
    plan = plan_trip(100.0, v, [])
    assert not plan.feasible and plan.max_reachable_km == 0


def test_naive_baseline_is_not_cheaper_than_optimised():
    v = creta()
    total = 1400.0
    cands = stations(total, 15, ["petrol"], detour=3.0) + stations(total, 60, ["petrol"], start_id=500, offset=20, detour=0.1)
    opt = plan_trip(total, v, cands)
    naive = naive_plan(total, v, cands)
    assert opt.feasible and naive is not None
    assert opt.energy_cost_inr <= naive.energy_cost_inr + 1e-6
