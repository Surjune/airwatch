"""add alert delivery state

Revision ID: 69ea060f709c
Revises: 601e9ab6385e
Create Date: 2026-09-12 22:31:45.253102

"""
from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69ea060f709c'
down_revision: Union[str, Sequence[str], None] = '601e9ab6385e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Separate recording an alert from delivering it.

    Until now an alert's only timestamp was when it was raised, so an alert
    nobody could be told about was indistinguishable from one an authority had
    received. Those are different findings: one is a silent authority, the other
    an unreachable one.
    """
    op.add_column('alerts', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('alerts', sa.Column('delivery_error', sa.String(length=512), nullable=True))


def downgrade() -> None:
    """Drop the delivery columns."""
    op.drop_column('alerts', 'delivery_error')
    op.drop_column('alerts', 'delivered_at')
