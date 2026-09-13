"""add citizen sensor readings

Revision ID: 54f34aeb2f01
Revises: 33613cb9d900
Create Date: 2026-09-13 18:30:11.874986

"""

from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "54f34aeb2f01"
down_revision: Union[str, Sequence[str], None] = "33613cb9d900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store readings citizens submit from their own sensors."""
    # The pollutant type already exists; creating it again would fail.
    pollutant = postgresql.ENUM(
        "pm25", "pm10", "no2", "so2", "o3", "co", "nh3", name="pollutant", create_type=False
    )
    op.create_table(
        "citizen_sensor_readings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("h3_cell", sa.String(length=15), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("sensor_model", sa.String(length=80), nullable=False),
        sa.Column("pollutant", pollutant, nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("reference_station_id", sa.Integer(), nullable=True),
        sa.Column("reference_value", sa.Float(), nullable=True),
        sa.Column("reference_distance_m", sa.Float(), nullable=True),
        sa.CheckConstraint("value >= 0", name="ck_citizen_sensor_value_non_negative"),
        sa.ForeignKeyConstraint(["reference_station_id"], ["stations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_citizen_sensor_readings_device_id"),
        "citizen_sensor_readings",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_citizen_sensor_readings_geom",
        "citizen_sensor_readings",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_citizen_sensor_readings_h3_cell"),
        "citizen_sensor_readings",
        ["h3_cell"],
        unique=False,
    )
    op.create_index(
        "ix_citizen_sensor_readings_observed",
        "citizen_sensor_readings",
        ["observed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the table. The pollutant type is shared, so it stays."""
    op.drop_index("ix_citizen_sensor_readings_observed", table_name="citizen_sensor_readings")
    op.drop_index(op.f("ix_citizen_sensor_readings_h3_cell"), table_name="citizen_sensor_readings")
    op.drop_index(
        "ix_citizen_sensor_readings_geom",
        table_name="citizen_sensor_readings",
        postgresql_using="gist",
    )
    op.drop_index(
        op.f("ix_citizen_sensor_readings_device_id"), table_name="citizen_sensor_readings"
    )
    op.drop_table("citizen_sensor_readings")
