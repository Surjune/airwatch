"""add measurement origin

Revision ID: e5f1a3b7c902
Revises: d4e9f2a6b358
Create Date: 2026-10-02 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f1a3b7c902"
down_revision: Union[str, Sequence[str], None] = "d4e9f2a6b358"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Record which relay each reading came through; every existing one is OpenAQ's."""
    op.add_column(
        "measurements",
        sa.Column("origin", sa.String(length=16), server_default="openaq", nullable=False),
    )


def downgrade() -> None:
    """Drop the origin, and the readings only the backup feed supplied."""
    op.execute("DELETE FROM measurements WHERE origin <> 'openaq'")
    op.drop_column("measurements", "origin")
