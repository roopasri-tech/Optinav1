"""Data structures for range and trip planning.

Units
-----
petrol / diesel : litres (L),  efficiency km/L
cng             : kilograms (kg), efficiency km/kg
electric        : kilowatt-hours (kWh), efficiency km/kWh
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config.settings import settings

UNIT = {"petrol": "L", "diesel": "L", "cng": "kg", "electric": "kWh"}
EFF_UNIT = {"petrol": "km/L", "diesel": "km/L", "cng": "km/kg", "electric": "km/kWh"}
LABEL = {"petrol": "Petrol", "diesel": "Diesel", "cng": "CNG", "electric": "Electricity"}


@dataclass
class FuelSpec:
    """One energy store of a vehicle (a fuel tank or a battery)."""
    fuel_type: str          # petrol | diesel | cng | electric
    capacity: float         # L / kg / kWh
    current_pct: float      # 0-100
    efficiency: float       # km per unit (rated / typical real-world)
    price_per_unit: float   # INR per unit
    max_fill_pct: float = 100.0   # EVs are planned to charge to EV_MAX_CHARGE_PCT

    @property
    def current_units(self) -> float:
        """Energy on board right now."""
        return self.capacity * self.current_pct / 100.0

    @property
    def planning_km_per_unit(self) -> float:
        """Conservative km per unit used for feasibility (efficiency x safety factor)."""
        return self.efficiency * settings.SAFETY_FACTOR

    @property
    def usable_range_km(self) -> float:
        """usable_range = capacity x level x efficiency x safety_factor"""
        return self.current_units * self.planning_km_per_unit

    @property
    def max_fill_units(self) -> float:
        return self.capacity * self.max_fill_pct / 100.0

    @property
    def refill_range_km(self) -> float:
        """Conservative range after a normal refill/charge at a station."""
        return self.max_fill_units * self.planning_km_per_unit

    @property
    def cost_per_km(self) -> float:
        """Expected INR per km = price / efficiency."""
        return self.price_per_unit / self.efficiency

    @property
    def unit(self) -> str:
        return UNIT[self.fuel_type]


@dataclass
class VehicleSpec:
    vehicle_id: Optional[int]
    name: str
    vehicle_type: str
    fuels: List[FuelSpec]   # always ordered cheapest-per-km first

    @property
    def is_bifuel(self) -> bool:
        return len(self.fuels) >= 2

    @property
    def is_ev(self) -> bool:
        return self.fuels[0].fuel_type == "electric"

    @property
    def fuel_types(self) -> List[str]:
        return [f.fuel_type for f in self.fuels]

    @property
    def total_usable_range_km(self) -> float:
        """A bi-fuel car can drive on one tank and then the other, so ranges add up."""
        return sum(f.usable_range_km for f in self.fuels)

    def fuel(self, fuel_type: str) -> FuelSpec:
        for f in self.fuels:
            if f.fuel_type == fuel_type:
                return f
        raise KeyError(fuel_type)


@dataclass
class Candidate:
    """A facility where this vehicle can refuel/recharge, positioned along the route."""
    facility_id: int
    name: str
    latitude: float
    longitude: float
    km_along: float           # distance from the start along the route
    detour_km: float          # extra km (there and back) to reach it from the route
    fuels: List[str]          # vehicle fuels sold here
    charging_power_kw: Optional[float] = None
    source: str = "osm"
    address: str = ""


@dataclass
class Purchase:
    fuel_type: str
    quantity: float           # units bought
    unit: str
    cost_inr: float
    level_after_pct: float
    charge_minutes: float = 0.0


@dataclass
class Stop:
    facility_id: int
    name: str
    latitude: float
    longitude: float
    km_along: float
    detour_km: float
    source: str
    purchases: List[Purchase]
    arrival_pct: Dict[str, float]           # worst-case level on arrival (efficiency x safety factor)
    departure_pct: Dict[str, float]
    reason: str
    expected_arrival_pct: Dict[str, float] = field(default_factory=dict)  # at rated efficiency
    charging_power_kw: Optional[float] = None
    address: str = ""


@dataclass
class Leg:
    from_name: str
    to_name: str
    start_km: float
    end_km: float
    distance_km: float              # includes detour distance to/from stops
    fuel_km: Dict[str, float]       # km driven on each fuel (expected)
    cost_inr: float


@dataclass
class PlanResult:
    feasible: bool
    stops: List[Stop] = field(default_factory=list)
    legs: List[Leg] = field(default_factory=list)
    energy_cost_inr: float = 0.0       # cost of the fuel/energy burnt on this trip
    purchase_cost_inr: float = 0.0     # money paid at the recommended stops
    fuel_breakdown: Dict[str, dict] = field(default_factory=dict)
    driven_km: float = 0.0             # route km + detours
    arrival_pct: Dict[str, float] = field(default_factory=dict)
    stop_minutes: float = 0.0
    max_reachable_km: float = 0.0      # how far the vehicle can get (set when infeasible)
    message: str = ""
