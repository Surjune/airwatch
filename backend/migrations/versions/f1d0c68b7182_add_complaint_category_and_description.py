"""add complaint category and description

Revision ID: f1d0c68b7182
Revises: c6ac7c50cd2a
Create Date: 2026-09-13 20:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1d0c68b7182"
down_revision: Union[str, Sequence[str], None] = "c6ac7c50cd2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

complaint_category = postgresql.ENUM(
    "open_burning",
    "industrial_smoke",
    "construction_dust",
    "vehicle_exhaust",
    "crop_residue_burning",
    "road_dust",
    "other",
    name="complaint_category",
    create_type=False,
)

_TABLES = ("citizen_reports", "citizen_sensor_readings")


def upgrade() -> None:
    """Let a citizen submission say what the resident saw."""
    complaint_category.create(op.get_bind(), checkfirst=True)
    for table in _TABLES:
        op.add_column(table, sa.Column("category", complaint_category, nullable=True))
        op.add_column(table, sa.Column("description", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Drop the columns, then the type only they used."""
    for table in _TABLES:
        op.drop_column(table, "description")
        op.drop_column(table, "category")
    complaint_category.drop(op.get_bind(), checkfirst=True)
