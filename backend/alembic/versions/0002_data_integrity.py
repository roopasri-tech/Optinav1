"""Data integrity: remove invented demo facilities, add per-section fetch cache,
unique external ids, safer foreign keys, and trip details.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Earlier versions seeded hand-written facilities ("source = seed") whose names
    #    looked like real businesses. They were not verified, so remove them.
    #    Rows cached by the old Overpass code (ids like "osm_node_1") are dropped too:
    #    that query lost most node coordinates, so they are re-fetched cleanly.
    stale = ("source = 'seed' OR source IS NULL OR external_id IS NULL "
             "OR external_id LIKE 'osm\\_%' OR external_id LIKE 'ocm\\_%'")
    op.execute(f"UPDATE trip_stops SET facility_id = NULL WHERE facility_id IN (SELECT id FROM facilities WHERE {stale})")
    op.execute(f"DELETE FROM facilities WHERE {stale}")

    # 2. One row per external record.
    op.execute("""
        UPDATE trip_stops SET facility_id = NULL WHERE facility_id IN (
            SELECT a.id FROM facilities a JOIN facilities b
              ON a.external_id = b.external_id AND a.id > b.id)
    """)
    op.execute("""
        DELETE FROM facilities a USING facilities b
         WHERE a.external_id = b.external_id AND a.id > b.id
    """)
    op.drop_index("ix_facilities_external_id", table_name="facilities")
    op.create_index("ix_facilities_external_id", "facilities", ["external_id"], unique=True)
    op.create_index("ix_facilities_latitude", "facilities", ["latitude"])
    op.create_index("ix_facilities_longitude", "facilities", ["longitude"])
    op.alter_column("facilities", "source", server_default="osm")

    # 3. Cache of which route sections were fetched from which provider.
    op.create_table(
        "facility_fetches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_key", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(300), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_facility_fetches_section_key", "facility_fetches", ["section_key"])
    op.create_index("ix_facility_fetches_fetched_at", "facility_fetches", ["fetched_at"])

    # 4. Store the full optimisation result so GET /api/trips/{id} can return it.
    op.add_column("trip_plans", sa.Column("details", sa.JSON(), nullable=True))

    # 5. Deleting a vehicle/route must not fail because old trips reference it.
    op.drop_constraint("trip_plans_vehicle_id_fkey", "trip_plans", type_="foreignkey")
    op.create_foreign_key("trip_plans_vehicle_id_fkey", "trip_plans", "vehicles",
                          ["vehicle_id"], ["id"], ondelete="SET NULL")
    op.drop_constraint("trip_plans_route_id_fkey", "trip_plans", type_="foreignkey")
    op.create_foreign_key("trip_plans_route_id_fkey", "trip_plans", "routes",
                          ["route_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("trip_stops_trip_plan_id_fkey", "trip_stops", type_="foreignkey")
    op.create_foreign_key("trip_stops_trip_plan_id_fkey", "trip_stops", "trip_plans",
                          ["trip_plan_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("trip_stops_facility_id_fkey", "trip_stops", type_="foreignkey")
    op.create_foreign_key("trip_stops_facility_id_fkey", "trip_stops", "facilities",
                          ["facility_id"], ["id"], ondelete="SET NULL")

    # 6. One spelling for bi-fuel vehicles.
    op.execute("UPDATE vehicles SET fuel_type = 'bifuel' "
               "WHERE fuel_type IN ('bifuel_cng_petrol', 'cng_petrol', 'bi-fuel')")


def downgrade() -> None:
    op.drop_constraint("trip_stops_facility_id_fkey", "trip_stops", type_="foreignkey")
    op.create_foreign_key("trip_stops_facility_id_fkey", "trip_stops", "facilities", ["facility_id"], ["id"])
    op.drop_constraint("trip_stops_trip_plan_id_fkey", "trip_stops", type_="foreignkey")
    op.create_foreign_key("trip_stops_trip_plan_id_fkey", "trip_stops", "trip_plans", ["trip_plan_id"], ["id"])
    op.drop_constraint("trip_plans_route_id_fkey", "trip_plans", type_="foreignkey")
    op.create_foreign_key("trip_plans_route_id_fkey", "trip_plans", "routes", ["route_id"], ["id"])
    op.drop_constraint("trip_plans_vehicle_id_fkey", "trip_plans", type_="foreignkey")
    op.create_foreign_key("trip_plans_vehicle_id_fkey", "trip_plans", "vehicles", ["vehicle_id"], ["id"])
    op.drop_column("trip_plans", "details")
    op.drop_index("ix_facility_fetches_fetched_at", table_name="facility_fetches")
    op.drop_index("ix_facility_fetches_section_key", table_name="facility_fetches")
    op.drop_table("facility_fetches")
    op.drop_index("ix_facilities_longitude", table_name="facilities")
    op.drop_index("ix_facilities_latitude", table_name="facilities")
    op.drop_index("ix_facilities_external_id", table_name="facilities")
    op.create_index("ix_facilities_external_id", "facilities", ["external_id"])
