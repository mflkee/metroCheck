"""add raw_text to protocol_files

Revision ID: a0b1c2d3e4f5
Revises: m1n2o3p4q5r6
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('protocol_files', sa.Column('raw_text', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('protocol_files', 'raw_text')
