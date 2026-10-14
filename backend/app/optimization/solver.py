"""Trip energy planner: decides WHERE to stop and HOW MUCH to buy.

Approach (feasibility first, then cost)
---------------------------------------
* Positions along the route: start (km 0), candidate stations (sorted by km), destination.
* An edge i -> j means "drive from stop i straight to stop j without stopping".
  It is allowed only if the energy on board covers the distance using the
  CONSERVATIVE consumption  distance / (efficiency x SAFETY_FACTOR).
  Detours count: half the detour to leave stop i, half to reach stop j.
* At a stop the vehicle refills the fuels it chooses to the normal fill level
  (100 % for tanks, EV_MAX_CHARGE_PCT for batteries).
* Bi-fuel cars burn the cheaper-per-km fuel first (how CNG cars normally run).
* Dijkstra minimises:   expected energy cost (rated efficiency)
                       + time value of each stop (stop time + charging time).
  The time value only RANKS plans; it is never reported as money.
* If the destination is unreachable we return feasible=False plus how far the
  vehicle can get - never a zero-cost plan.

After the search, the chosen stop sequence is re-simulated (`evaluate_plan`) to
produce quantities, costs and levels, and `validate_plan` checks the result.
"""
import heapq
import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.config.settings import settings
from app.optimization.cost import (
    charging_minutes, cost_of_km, drive_cheapest_first, units_for_distance,
)
from app.optimization.state import (
    LABEL, UNIT, Candidate, Leg, PlanResult, Purchase, Stop, VehicleSpec,
)

BINS_SINGLE = 40          # fuel-level buckets used to merge equivalent search states
BINS_MULTI = 12
MAX_CANDIDATES_SINGLE = 220
MAX_CANDIDATES_MULTI = 110


class PlanIntegrityError(Exception):
    """Raised when a plan fails its own consistency checks."""


# ─── Candidate preparation ────────────────────────────────────────────────────

def prepare_candidates(spec: VehicleSpec, candidates: Sequence[Candidate], total_km: float) -> List[Candidate]:
    """Keep stations that sell a fuel this vehicle uses and lie inside the trip;
    then thin them so that each window of route keeps its lowest-detour option."""
    usable = []
    for c in candidates:
        fuels = [ft for ft in c.fuels if ft in spec.fuel_types]
        if not fuels or not (0.5 <= c.km_along <= total_km - 0.5):
            continue
        usable.append(Candidate(**{**c.__dict__, "fuels": fuels}))

    cap = MAX_CANDIDATES_SINGLE if len(spec.fuels) == 1 else MAX_CANDIDATES_MULTI
    window = 4.0 if len(spec.fuels) == 1 else 8.0
    while True:
        best: Dict[tuple, Candidate] = {}
        for c in usable:
            key = (int(c.km_along // window), tuple(sorted(c.fuels)))
            cur = best.get(key)
            if cur is None or (c.detour_km, c.facility_id) < (cur.detour_km, cur.facility_id):
                best[key] = c
        thinned = sorted(best.values(), key=lambda c: (c.km_along, c.facility_id))
        if len(thinned) <= cap:
            return thinned
        window *= 1.5


# ─── Search ───────────────────────────────────────────────────────────────────

@dataclass
class _Label:
    cost: float
    units: Tuple[float, ...]
    parent: Optional[tuple]
    refill: Tuple[int, ...]      # indices of fuels refilled at this node


FEWEST_STOPS_PENALTY_INR = 100_000.0   # dominates any fuel saving -> minimises stop count
# Tie-breaker: among equally priced plans prefer refuelling when the tank is getting
# low rather than topping up a nearly full tank (INR per km of safe range left on arrival).
EARLY_STOP_PENALTY_PER_KM = 0.05


def plan_trip(total_km: float, spec: VehicleSpec, candidates: Sequence[Candidate],
              preference: str = "cheapest") -> PlanResult:
    """preference: 'cheapest' (lowest energy cost, small time penalty per stop)
                   'fewest_stops' (minimum number of stops, then lowest cost)."""
    extra_stop_penalty = FEWEST_STOPS_PENALTY_INR if preference == "fewest_stops" else 0.0
    fuels = spec.fuels
    cands = prepare_candidates(spec, candidates, total_km)
    n = len(cands)
    dest = n + 1
    km = [0.0] + [c.km_along for c in cands] + [total_km]
    det = [0.0] + [c.detour_km for c in cands] + [0.0]
    bins = BINS_SINGLE if len(fuels) == 1 else BINS_MULTI
    time_value = settings.TIME_VALUE_INR_PER_MIN

    def key(node: int, units: Sequence[float]) -> tuple:
        return (node,) + tuple(min(bins, int(u / f.capacity * bins + 1e-9)) for u, f in zip(units, fuels))

    start_units = tuple(f.current_units for f in fuels)
    k0 = key(0, start_units)
    labels: Dict[tuple, _Label] = {k0: _Label(0.0, start_units, None, ())}
    counter = itertools.count()
    heap = [(0.0, next(counter), k0)]
    goal: Optional[tuple] = None

    def push(k: tuple, lab: _Label):
        cur = labels.get(k)
        if cur is None or lab.cost < cur.cost - 1e-9:
            labels[k] = lab
            heapq.heappush(heap, (lab.cost, next(counter), k))

    while heap:
        cost, _, k = heapq.heappop(heap)
        lab = labels[k]
        if cost > lab.cost + 1e-9:
            continue
        node = k[0]
        if node == dest:
            goal = k
            break
        state_range = sum(u * f.planning_km_per_unit for u, f in zip(lab.units, fuels))
        for j in range(node + 1, dest + 1):
            base = km[j] - km[node]
            if base > state_range + 1e-6:
                break                              # every later node is farther still
            dist = base + det[node] / 2 + det[j] / 2
            left, km_by = drive_cheapest_first(list(lab.units), fuels, dist, conservative=True)
            if left is None:
                continue
            new_cost = cost + cost_of_km(km_by, fuels)
            if j == dest:
                push(key(dest, left), _Label(new_cost, tuple(left), k, ()))
                continue
            cand = cands[j - 1]
            sold = [i for i, f in enumerate(fuels) if f.fuel_type in cand.fuels]
            arrival_range = sum(u * f.planning_km_per_unit for u, f in zip(left, fuels))
            for r in range(1, len(sold) + 1):
                for subset in itertools.combinations(sold, r):
                    after = list(left)
                    minutes = settings.STOP_TIME_MIN
                    useful = True
                    for i in subset:
                        f = fuels[i]
                        if after[i] >= f.max_fill_units - 1e-6:
                            useful = False         # nothing to add for this fuel
                            break
                        added = f.max_fill_units - after[i]
                        after[i] = f.max_fill_units
                        if f.fuel_type == "electric":
                            minutes += charging_minutes(added, cand.charging_power_kw)
                    if useful:
                        penalty = (minutes * time_value + extra_stop_penalty
                                   + EARLY_STOP_PENALTY_PER_KM * arrival_range)
                        push(key(j, after), _Label(new_cost + penalty, tuple(after), k, subset))

    if goal is None:
        reach = 0.0
        for k, lab in labels.items():
            node = k[0]
            r = km[node] + sum(u * f.planning_km_per_unit for u, f in zip(lab.units, fuels)) - det[node] / 2
            reach = max(reach, r)
        return PlanResult(feasible=False, max_reachable_km=round(min(reach, total_km), 1),
                          message="No feasible sequence of stops was found.")

    # Reconstruct the chosen stops.
    sequence: List[Tuple[Candidate, Tuple[int, ...]]] = []
    k = goal
    while labels[k].parent is not None:
        node = k[0]
        if node != dest:
            sequence.append((cands[node - 1], labels[k].refill))
        k = labels[k].parent
    sequence.reverse()
    return evaluate_plan(total_km, spec, sequence)


# ─── Plan evaluation (quantities, costs, levels) ─────────────────────────────

def _last_stop_targets(spec: VehicleSpec, units: List[float], refill: Sequence[int], remaining_km: float) -> Dict[int, float]:
    """At the final stop buy only what the rest of the trip needs (conservatively),
    using the cheaper fuel first; never more than the normal fill level."""
    need_km = remaining_km
    targets: Dict[int, float] = {}
    for i, f in enumerate(spec.fuels):
        if i in refill:
            want = need_km / f.planning_km_per_unit
            targets[i] = min(f.max_fill_units, max(units[i], want))
            need_km -= targets[i] * f.planning_km_per_unit
        else:
            need_km -= units[i] * f.planning_km_per_unit
        need_km = max(0.0, need_km)
    return targets


def _pct(units: Sequence[float], spec: VehicleSpec) -> Dict[str, float]:
    return {f.fuel_type: round(100.0 * u / f.capacity, 1) for u, f in zip(units, spec.fuels)}


def evaluate_plan(total_km: float, spec: VehicleSpec,
                  sequence: Sequence[Tuple[Candidate, Sequence[int]]]) -> PlanResult:
    """Simulate a stop sequence.

    * Conservative simulation (efficiency x SAFETY_FACTOR) gives the levels shown
      at each stop and the quantities to buy - this is what keeps the plan safe.
    * Expected simulation (rated efficiency) gives the energy actually burnt and
      therefore the trip's energy cost.
    """
    fuels = spec.fuels
    plan_units = [f.current_units for f in fuels]
    exp_units = [f.current_units for f in fuels]
    stops: List[Stop] = []
    legs: List[Leg] = []
    breakdown = {f.fuel_type: {"km": 0.0, "quantity": 0.0, "unit": f.unit, "cost_inr": 0.0} for f in fuels}
    purchase_total = 0.0
    stop_minutes = 0.0

    pos_km, pos_det, pos_name = 0.0, 0.0, "Start"
    waypoints = list(sequence) + [(None, ())]
    for idx, (cand, refill) in enumerate(waypoints):
        to_km = total_km if cand is None else cand.km_along
        to_det = 0.0 if cand is None else cand.detour_km
        to_name = "Destination" if cand is None else cand.name
        dist = (to_km - pos_km) + pos_det / 2 + to_det / 2
        if dist < -1e-6:
            raise PlanIntegrityError("Stops are not in route order.")

        plan_left, _ = drive_cheapest_first(plan_units, fuels, dist, conservative=True)
        if plan_left is None:
            raise PlanIntegrityError(f"Leg to {to_name} exceeds the vehicle's safe range.")
        exp_left, exp_km = drive_cheapest_first(exp_units, fuels, dist, conservative=False)
        if exp_left is None:   # cannot happen when the conservative check passed
            raise PlanIntegrityError("Expected-consumption simulation ran out of energy.")
        leg_cost = cost_of_km(exp_km, fuels)
        for ft, kmv in exp_km.items():
            f = spec.fuel(ft)
            breakdown[ft]["km"] += kmv
            breakdown[ft]["quantity"] += units_for_distance(kmv, f)
            breakdown[ft]["cost_inr"] += kmv * f.cost_per_km
        legs.append(Leg(pos_name, to_name, round(pos_km, 1), round(to_km, 1), round(dist, 1),
                        {k: round(v, 1) for k, v in exp_km.items()}, round(leg_cost, 2)))
        plan_units, exp_units = plan_left, exp_left
        if cand is None:
            break

        arrival = _pct(plan_units, spec)
        expected_arrival = _pct(exp_units, spec)
        arrival_range = sum(u * f.planning_km_per_unit for u, f in zip(plan_units, fuels))
        is_last = idx == len(sequence) - 1
        if is_last:
            targets = _last_stop_targets(spec, plan_units, refill, total_km - cand.km_along + cand.detour_km / 2)
        else:
            targets = {i: fuels[i].max_fill_units for i in refill}

        purchases: List[Purchase] = []
        for i, target in targets.items():
            f = fuels[i]
            qty = max(0.0, target - plan_units[i])
            if qty < 0.05:
                continue
            minutes = charging_minutes(qty, cand.charging_power_kw) if f.fuel_type == "electric" else 0.0
            cost = qty * f.price_per_unit
            purchases.append(Purchase(f.fuel_type, round(qty, 2), f.unit, round(cost, 2),
                                      round(100.0 * target / f.capacity, 1), round(minutes, 1)))
            purchase_total += cost
            stop_minutes += minutes
            plan_units[i] = target
            exp_units[i] = max(exp_units[i], target)
        if not purchases:
            raise PlanIntegrityError(f"Stop at {cand.name} buys nothing.")
        stop_minutes += settings.STOP_TIME_MIN

        next_cand = waypoints[idx + 1][0]
        next_name = "the destination" if next_cand is None else next_cand.name
        next_km = (total_km if next_cand is None else next_cand.km_along) - cand.km_along
        bought = ", ".join(f"{p.quantity:g} {p.unit} {LABEL[p.fuel_type]}" for p in purchases)
        # Is this stop needed to reach the next stop, or only chosen because it is cheaper?
        needed_for_range = arrival_range + 1e-6 < next_km + cand.detour_km / 2
        cheap = fuels[0]
        if needed_for_range or not spec.is_bifuel:
            reason = (f"Required: you arrive with about {arrival_range:.0f} km of safe range (worst case), "
                      f"less than the {next_km:.0f} km to {next_name}. Buy {bought} here.")
        else:
            reason = (f"Optional for range (about {arrival_range:.0f} km of safe range left), but it saves money: "
                      f"buy {bought} for the next {next_km:.0f} km to {next_name}.")
        if spec.is_bifuel and any(p.fuel_type == cheap.fuel_type for p in purchases):
            reason += (f" {LABEL[cheap.fuel_type]} costs ₹{cheap.cost_per_km:.2f}/km versus "
                       f"₹{fuels[1].cost_per_km:.2f}/km for {LABEL[fuels[1].fuel_type]}.")

        stops.append(Stop(
            facility_id=cand.facility_id, name=cand.name, latitude=cand.latitude, longitude=cand.longitude,
            km_along=round(cand.km_along, 1), detour_km=round(cand.detour_km, 1), source=cand.source,
            purchases=purchases, arrival_pct=arrival, departure_pct=_pct(plan_units, spec), reason=reason,
            expected_arrival_pct=expected_arrival,
            charging_power_kw=cand.charging_power_kw, address=cand.address,
        ))
        pos_km, pos_det, pos_name = cand.km_along, cand.detour_km, cand.name

    for b in breakdown.values():
        b["km"] = round(b["km"], 1)
        b["quantity"] = round(b["quantity"], 2)
        b["cost_inr"] = round(b["cost_inr"], 2)
    breakdown = {k: v for k, v in breakdown.items() if v["km"] > 0}
    energy = sum(b["cost_inr"] for b in breakdown.values())

    result = PlanResult(
        feasible=True, stops=stops, legs=legs,
        energy_cost_inr=round(energy, 2), purchase_cost_inr=round(purchase_total, 2),
        fuel_breakdown=breakdown, driven_km=round(sum(l.distance_km for l in legs), 1),
        arrival_pct=_pct(exp_units, spec), stop_minutes=round(stop_minutes, 1),
        max_reachable_km=total_km,
    )
    validate_plan(total_km, spec, result)
    return result


# ─── Sanity checks ────────────────────────────────────────────────────────────

def validate_plan(total_km: float, spec: VehicleSpec, plan: PlanResult) -> None:
    """Reject results that are physically or mathematically impossible."""
    if not plan.feasible:
        return
    if total_km > spec.total_usable_range_km + 1e-6 and not plan.stops:
        raise PlanIntegrityError("Trip is longer than the usable range but no stop was planned.")
    if total_km > 0 and plan.energy_cost_inr <= 0:
        raise PlanIntegrityError("A trip that uses energy cannot cost ₹0.")
    if plan.energy_cost_inr < 0 or plan.purchase_cost_inr < 0:
        raise PlanIntegrityError("Negative cost.")
    km_sum = sum(b["km"] for b in plan.fuel_breakdown.values())
    if abs(km_sum - plan.driven_km) > 0.5 + 0.001 * plan.driven_km:
        raise PlanIntegrityError("Fuel breakdown does not add up to the distance driven.")
    if plan.driven_km + 0.5 < total_km:
        raise PlanIntegrityError("Planned distance is shorter than the route.")
    for s in plan.stops:
        for p in s.purchases:
            f = spec.fuel(p.fuel_type)
            if p.quantity > f.capacity + 1e-6:
                raise PlanIntegrityError("Purchase exceeds tank/battery capacity.")


# ─── Baselines ────────────────────────────────────────────────────────────────

def naive_plan(total_km: float, spec: VehicleSpec, candidates: Sequence[Candidate]) -> Optional[PlanResult]:
    """'Without SmartRoute': drive until the safe range is nearly used up and stop at
    the farthest station still in range, ignoring detours. None if that fails."""
    cands = sorted((c for c in candidates
                    if any(ft in spec.fuel_types for ft in c.fuels) and 0.5 <= c.km_along <= total_km - 0.5),
                   key=lambda c: c.km_along)
    units = [f.current_units for f in spec.fuels]
    pos_km, pos_det = 0.0, 0.0
    sequence: List[Tuple[Candidate, Tuple[int, ...]]] = []
    for _ in range(200):
        rng = sum(u * f.planning_km_per_unit for u, f in zip(units, spec.fuels))
        if total_km - pos_km + pos_det / 2 <= rng:
            try:
                return evaluate_plan(total_km, spec, sequence)
            except PlanIntegrityError:
                return None
        reachable = [c for c in cands if c.km_along > pos_km + 0.1
                     and (c.km_along - pos_km) + pos_det / 2 + c.detour_km / 2 <= rng]
        if not reachable:
            return None
        nxt = reachable[-1]
        left, _ = drive_cheapest_first(units, spec.fuels, (nxt.km_along - pos_km) + pos_det / 2 + nxt.detour_km / 2, True)
        refill = tuple(i for i, f in enumerate(spec.fuels) if f.fuel_type in nxt.fuels)
        units = [f.max_fill_units if i in refill else left[i] for i, f in enumerate(spec.fuels)]
        sequence.append((nxt, refill))
        pos_km, pos_det = nxt.km_along, nxt.detour_km
    return None
