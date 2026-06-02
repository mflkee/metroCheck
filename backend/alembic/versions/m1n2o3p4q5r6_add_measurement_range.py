"""add measurement_range to protocol_data

Revision ID: m1n2o3p4q5r6
Revises: i2j4k6l8m0n2
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm1n2o3p4q5r6'
down_revision: Union[str, None] = 'i2j4k6l8m0n2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('protocol_data', sa.Column('measurement_range', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('protocol_data', 'measurement_range')
