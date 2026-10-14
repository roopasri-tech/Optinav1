"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("vehicle_type", sa.String(60), nullable=False, server_default="car"),
        sa.Column("fuel_type", sa.String(30), nullable=False),
        sa.Column("secondary_fuel_type", sa.String(30), nullable=True),
        sa.Column("tank_capacity", sa.Float(), nullable=False, server_default="40.0"),
        sa.Column("efficiency", sa.Float(), nullable=False, server_default="15.0"),
        sa.Column("current_fuel_pct", sa.Float(), nullable=False, server_default="100.0"),
        sa.Column("cng_tank_capacity", sa.Float(), nullable=True),
        sa.Column("cng_efficiency", sa.Float(), nullable=True),
        sa.Column("current_cng_pct", sa.Float(), nullable=True),
        sa.Column("battery_capacity_kwh", sa.Float(), nullable=True),
        sa.Column("ev_efficiency", sa.Float(), nullable=True),
        sa.Column("current_battery_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicles_id", "vehicles", ["id"])

    op.create_table(
        "facilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address", sa.String(400), nullable=True),
        sa.Column("fuel_types", sa.JSON(), nullable=True),
        sa.Column("connector_types", sa.JSON(), nullable=True),
        sa.Column("charging_power_kw", sa.Float(), nullable=True),
        sa.Column("num_chargers", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="seed"),
        sa.Column("is_operational", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_facilities_id", "facilities", ["id"])
    op.create_index("ix_facilities_external_id", "facilities", ["external_id"])
    op.create_index("ix_facilities_category", "facilities", ["category"])

    op.create_table(
        "fuel_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fuel_type", sa.String(30), nullable=False),
        sa.Column("price_per_unit", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fuel_type"),
    )

    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("destination_name", sa.String(200), nullable=False),
        sa.Column("source_lat", sa.Float(), nullable=False),
        sa.Column("source_lon", sa.Float(), nullable=False),
        sa.Column("dest_lat", sa.Float(), nullable=False),
        sa.Column("dest_lon", sa.Float(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("duration_min", sa.Float(), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False, server_default="osrm"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_routes_id", "routes", ["id"])

    op.create_table(
        "trip_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("strategy", sa.String(60), nullable=False),
        sa.Column("total_cost_inr", sa.Float(), nullable=False),
        sa.Column("baseline_cost_inr", sa.Float(), nullable=True),
        sa.Column("savings_inr", sa.Float(), nullable=True),
        sa.Column("fuel_breakdown", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_plans_id", "trip_plans", ["id"])

    op.create_table(
        "trip_stops",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_plan_id", sa.Integer(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.Column("stop_order", sa.Integer(), nullable=False),
        sa.Column("stop_type", sa.String(30), nullable=False),
        sa.Column("fuel_type", sa.String(30), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("cost_inr", sa.Float(), nullable=True),
        sa.Column("detour_km", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(["trip_plan_id"], ["trip_plans.id"]),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("trip_stops")
    op.drop_table("trip_plans")
    op.drop_table("routes")
    op.drop_table("fuel_prices")
    op.drop_table("facilities")
    op.drop_table("vehicles")
