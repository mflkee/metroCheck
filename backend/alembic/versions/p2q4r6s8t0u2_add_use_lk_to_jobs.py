"""add use_lk to jobs

Revision ID: p2q4r6s8t0u2
Revises: 07002a2b1f9a
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p2q4r6s8t0u2'
down_revision: Union[str, None] = '07002a2b1f9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('use_lk', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column('jobs', 'use_lk')
