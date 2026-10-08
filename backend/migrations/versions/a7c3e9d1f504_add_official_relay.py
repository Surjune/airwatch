"""add official relay

Revision ID: a7c3e9d1f504
Revises: e5f1a3b7c902
Create Date: 2026-10-08 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c3e9d1f504"
down_revision: Union[str, Sequence[str], None] = "e5f1a3b7c902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Record where each official sub-index was read; every existing one is data.gov.in's."""
    op.add_column(
        "official_sub_indices",
        sa.Column("relay", sa.String(length=16), server_default="data.gov.in", nullable=False),
    )


def downgrade() -> None:
    """Drop the relay, and the sub-indices only TNPCB's website supplied."""
    op.execute("DELETE FROM official_sub_indices WHERE relay <> 'data.gov.in'")
    op.drop_column("official_sub_indices", "relay")
