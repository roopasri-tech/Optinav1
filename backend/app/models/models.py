from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    vehicle_type: Mapped[str] = mapped_column(String(60))  # car, bike, truck, bus
    # petrol | diesel | cng | electric | bifuel (CNG + petrol)
    fuel_type: Mapped[str] = mapped_column(String(30))
    secondary_fuel_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Liquid fuel tank (petrol / diesel, or the petrol tank of a bi-fuel car).
    # For a CNG-only vehicle these hold the CNG tank (kg, km/kg).
    tank_capacity: Mapped[float] = mapped_column(Float, default=40.0)
    efficiency: Mapped[float] = mapped_column(Float, default=15.0)  # km per unit
    current_fuel_pct: Mapped[float] = mapped_column(Float, default=100.0)

    # CNG tank of a bi-fuel vehicle
    cng_tank_capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # kg
    cng_efficiency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # km/kg
    current_cng_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # EV battery
    battery_capacity_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ev_efficiency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # km/kWh
    current_battery_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Facility(Base):
    """A real-world facility from an external provider (OpenStreetMap / Open Charge Map)."""
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), index=True)  # fuel, ev, restaurant, parking, restroom
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)

    fuel_types: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)       # ["petrol","diesel","cng"]
    connector_types: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    charging_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_chargers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    source: Mapped[str] = mapped_column(String(30), default="osm")  # osm | ocm
    is_operational: Mapped[bool] = mapped_column(Boolean, default=True)
    # website, phone, opening_hours, brand, operator, fuel_types_inferred, ...
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FacilityFetch(Base):
    """Cache record: one route section fetched from one provider."""
    __tablename__ = "facility_fetches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_key: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(20))       # osm | ocm
    status: Mapped[str] = mapped_column(String(20))         # ok | failed
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class FuelPrice(Base):
    __tablename__ = "fuel_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fuel_type: Mapped[str] = mapped_column(String(30), unique=True)
    price_per_unit: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_name: Mapped[str] = mapped_column(String(200))
    destination_name: Mapped[str] = mapped_column(String(200))
    source_lat: Mapped[float] = mapped_column(Float)
    source_lon: Mapped[float] = mapped_column(Float)
    dest_lat: Mapped[float] = mapped_column(Float)
    dest_lon: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)
    duration_min: Mapped[float] = mapped_column(Float)
    geometry: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # GeoJSON LineString [lon, lat]
    provider: Mapped[str] = mapped_column(String(30), default="osrm")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trip_plans: Mapped[list["TripPlan"]] = relationship(
        "TripPlan", back_populates="route", cascade="all, delete-orphan", passive_deletes=True)


class TripPlan(Base):
    __tablename__ = "trip_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True)
    strategy: Mapped[str] = mapped_column(String(60))
    total_cost_inr: Mapped[float] = mapped_column(Float)
    baseline_cost_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    savings_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fuel_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # full API result
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    route: Mapped["Route"] = relationship("Route", back_populates="trip_plans")
    stops: Mapped[list["TripStop"]] = relationship(
        "TripStop", back_populates="trip_plan", cascade="all, delete-orphan", passive_deletes=True)


class TripStop(Base):
    __tablename__ = "trip_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_plan_id: Mapped[int] = mapped_column(ForeignKey("trip_plans.id", ondelete="CASCADE"))
    facility_id: Mapped[Optional[int]] = mapped_column(ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True)
    stop_order: Mapped[int] = mapped_column(Integer)
    stop_type: Mapped[str] = mapped_column(String(30))  # fuel, ev
    fuel_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detour_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    trip_plan: Mapped["TripPlan"] = relationship("TripPlan", back_populates="stops")
