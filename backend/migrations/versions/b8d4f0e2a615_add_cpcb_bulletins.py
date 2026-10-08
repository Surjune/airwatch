"""add cpcb bulletins

Revision ID: b8d4f0e2a615
Revises: a7c3e9d1f504
Create Date: 2026-10-08 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b8d4f0e2a615"
down_revision: Union[str, Sequence[str], None] = "a7c3e9d1f504"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store each city's line in CPCB's daily AQI bulletin."""
    op.create_table(
        "cpcb_bulletins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("aqi", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("prominent_pollutants", postgresql.ARRAY(sa.String(length=8)), nullable=False),
        sa.Column("stations_reporting", sa.Integer(), nullable=False),
        sa.Column("stations_total", sa.Integer(), nullable=False),
        sa.CheckConstraint("aqi >= 0", name="ck_bulletin_aqi_non_negative"),
        sa.CheckConstraint(
            "stations_reporting <= stations_total", name="ck_bulletin_stations_within_total"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("city", "day", name="uq_bulletin_city_day"),
    )


def downgrade() -> None:
    """Drop the bulletins."""
    op.drop_table("cpcb_bulletins")
