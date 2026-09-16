"""add description translations

Revision ID: d4e9f2a6b358
Revises: c3d8e5f1a247
Create Date: 2026-09-16 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e9f2a6b358"
down_revision: Union[str, Sequence[str], None] = "c3d8e5f1a247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store English translations of residents' descriptions, keyed by the text's hash."""
    op.create_table(
        "description_translations",
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("is_english", sa.Boolean(), nullable=False),
        sa.Column("english", sa.String(length=1500), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("text_sha256"),
    )


def downgrade() -> None:
    """Drop the translations; each is made again on the next report download."""
    op.drop_table("description_translations")
