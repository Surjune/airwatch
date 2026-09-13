"""add authority is active

Revision ID: 33613cb9d900
Revises: 03c435e12a17
Create Date: 2026-09-13 15:16:27.753861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33613cb9d900'
down_revision: Union[str, Sequence[str], None] = '03c435e12a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Let an authority be retired from routing without losing the alerts it received."""
    op.add_column('authorities', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Drop the flag."""
    op.drop_column('authorities', 'is_active')
