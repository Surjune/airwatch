"""add alert kind for coordination requests

Revision ID: c6ac7c50cd2a
Revises: 54f34aeb2f01
Create Date: 2026-09-13 18:38:50.635294

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c6ac7c50cd2a"
down_revision: Union[str, Sequence[str], None] = "54f34aeb2f01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

alert_kind = postgresql.ENUM("local", "coordination", name="alert_kind", create_type=False)


def upgrade() -> None:
    """Record whether an alert is local or a request to a neighbouring jurisdiction."""
    # add_column does not create a native enum type, so it is created first.
    alert_kind.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "alerts",
        sa.Column("kind", alert_kind, server_default="local", nullable=False),
    )
    op.add_column("alerts", sa.Column("source_name", sa.String(length=256), nullable=True))
    op.add_column("alerts", sa.Column("source_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop the columns, then the type nothing else uses."""
    op.drop_column("alerts", "source_confidence")
    op.drop_column("alerts", "source_name")
    op.drop_column("alerts", "kind")
    alert_kind.drop(op.get_bind(), checkfirst=True)
