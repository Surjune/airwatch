"""add model concentrations

Revision ID: c3d8e5f1a247
Revises: b7e2c41d9a36
Create Date: 2026-09-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3d8e5f1a247"
down_revision: Union[str, Sequence[str], None] = "b7e2c41d9a36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

pollutant = postgresql.ENUM(name="pollutant", create_type=False)


def upgrade() -> None:
    """Store the CAMS regional model's hourly concentrations per pilot city."""
    op.create_table(
        "model_concentrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(length=32), nullable=False),
        sa.Column("pollutant", pollutant, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("is_forecast", sa.Boolean(), nullable=False),
        sa.Column("grid_longitude", sa.Float(), nullable=False),
        sa.Column("grid_latitude", sa.Float(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "city", "pollutant", "observed_at", name="uq_model_city_pollutant_hour"
        ),
    )
    op.create_index(
        "ix_model_concentrations_city_time", "model_concentrations", ["city", "observed_at"]
    )


def downgrade() -> None:
    """Drop the model table; it is refilled on the next ingest."""
    op.drop_index("ix_model_concentrations_city_time", table_name="model_concentrations")
    op.drop_table("model_concentrations")
