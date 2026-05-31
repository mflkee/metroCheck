"""Add phase_stats to jobs

Revision ID: e7f3g5h8i9j0
Revises: d1a2b3c4e5f6
Create Date: 2026-05-31 18:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f3g5h8i9j0'
down_revision: Union[str, None] = 'd1a2b3c4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('phase_stats', sa.JSON(), nullable=True))
    op.add_column('jobs', sa.Column('current_phase', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'current_phase')
    op.drop_column('jobs', 'phase_stats')
