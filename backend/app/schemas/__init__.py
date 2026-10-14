from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Pct = Optional[float]


class LocationInput(BaseModel):
    query: str = Field("", max_length=300)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def need_something(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be given together")
        if self.lat is None and not self.query.strip():
            raise ValueError("a place name or coordinates are required")
        return self


class RoutePlanRequest(BaseModel):
    source: LocationInput
    destination: LocationInput


class VehicleBase(BaseModel):
    vehicle_type: Optional[str] = Field(None, max_length=60)
    fuel_type: Optional[str] = Field(None, max_length=30)
    tank_capacity: Optional[float] = Field(None, gt=0, le=1000)
    efficiency: Optional[float] = Field(None, gt=0, le=200)
    current_fuel_pct: Pct = Field(None, ge=0, le=100)
    cng_tank_capacity: Optional[float] = Field(None, gt=0, le=200)
    cng_efficiency: Optional[float] = Field(None, gt=0, le=200)
    current_cng_pct: Pct = Field(None, ge=0, le=100)
    battery_capacity_kwh: Optional[float] = Field(None, gt=0, le=300)
    ev_efficiency: Optional[float] = Field(None, gt=0, le=50)
    current_battery_pct: Pct = Field(None, ge=0, le=100)


class VehicleCreate(VehicleBase):
    name: str = Field(..., min_length=1, max_length=120)
    vehicle_type: str = Field("car", max_length=60)
    fuel_type: str = Field("petrol", max_length=30)
    current_fuel_pct: float = Field(100.0, ge=0, le=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class VehicleUpdate(VehicleBase):
    name: Optional[str] = Field(None, min_length=1, max_length=120)


class OptimizationRequest(BaseModel):
    vehicle_id: int
    route_id: Optional[int] = None            # preferred: optimise the route already on screen
    source: Optional[LocationInput] = None
    destination: Optional[LocationInput] = None
    preference: str = Field("cheapest", pattern="^(cheapest|fewest_stops)$")
    current_fuel_pct: Pct = Field(None, ge=0, le=100)
    current_cng_pct: Pct = Field(None, ge=0, le=100)
    current_battery_pct: Pct = Field(None, ge=0, le=100)
    petrol_price: Optional[float] = Field(None, gt=0, le=500)
    diesel_price: Optional[float] = Field(None, gt=0, le=500)
    cng_price: Optional[float] = Field(None, gt=0, le=500)
    electricity_price: Optional[float] = Field(None, gt=0, le=200)

    @model_validator(mode="after")
    def route_or_places(self):
        if self.route_id is None and (self.source is None or self.destination is None):
            raise ValueError("give route_id, or both source and destination")
        return self


class NearRouteRequest(BaseModel):
    route_id: Optional[int] = None
    geometry: Optional[List[List[float]]] = None   # [[lat, lon], ...] if no route_id
    distance_km: Optional[float] = Field(None, gt=0)
    category: Optional[str] = None
    wait: bool = True

    @model_validator(mode="after")
    def route_or_geometry(self):
        if self.route_id is None and not self.geometry:
            raise ValueError("give route_id or geometry")
        if self.geometry is not None:
            if len(self.geometry) < 2 or any(len(p) != 2 for p in self.geometry):
                raise ValueError("geometry must be a list of [lat, lon] pairs")
            if len(self.geometry) > 20000:
                raise ValueError("geometry has too many points")
        return self
