"""add alert briefs

Revision ID: b7e2c41d9a36
Revises: a93e4b7d20c5
Create Date: 2026-09-14 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e2c41d9a36"
down_revision: Union[str, Sequence[str], None] = "a93e4b7d20c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store one Gemini-written brief per alert."""
    op.create_table(
        "alert_briefs",
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(length=800), nullable=False),
        sa.Column("suggested_action", sa.String(length=400), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("alert_id"),
    )


def downgrade() -> None:
    """Drop the briefs; they are rewritten on request."""
    op.drop_table("alert_briefs")
