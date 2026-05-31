"""Add calibration_cache table

Revision ID: h1i3j5k7l9m1
Revises: g9h2i4j6k8l0
Create Date: 2026-05-31 06:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h1i3j5k7l9m1'
down_revision: Union[str, None] = 'g9h2i4j6k8l0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'calibration_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('total_records', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_fetched', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year')
    )


def downgrade() -> None:
    op.drop_table('calibration_cache')
