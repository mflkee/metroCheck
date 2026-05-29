"""Add missing job columns

Revision ID: d1a2b3c4e5f6
Revises: b5e2a8c4d1f3
Create Date: 2026-05-29 08:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a2b3c4e5f6'
down_revision: Union[str, None] = 'b5e2a8c4d1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('total_devices', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('processed_devices', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('current_device', sa.String(length=255), nullable=True))
    op.add_column('jobs', sa.Column('health_status', sa.String(length=20), nullable=True))
    op.add_column('jobs', sa.Column('email_sent', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('jobs', 'email_sent')
    op.drop_column('jobs', 'health_status')
    op.drop_column('jobs', 'current_device')
    op.drop_column('jobs', 'processed_devices')
    op.drop_column('jobs', 'total_devices')
