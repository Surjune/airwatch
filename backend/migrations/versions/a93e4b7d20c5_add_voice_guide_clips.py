"""add voice guide clips

Revision ID: a93e4b7d20c5
Revises: f1d0c68b7182
Create Date: 2026-09-14 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a93e4b7d20c5"
down_revision: Union[str, Sequence[str], None] = "f1d0c68b7182"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store each synthesised paragraph of the voice guide once."""
    op.create_table(
        "voice_guide_clips",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("model", sa.String(length=32), nullable=False),
        sa.Column("speaker", sa.String(length=32), nullable=False),
        sa.Column("audio", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("cache_key"),
    )


def downgrade() -> None:
    """Drop the clips; they are regenerated on demand."""
    op.drop_table("voice_guide_clips")
