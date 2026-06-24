"""Add missing calibration columns

Revision ID: n3o4p5q6r7s8
Revises: m1n2o3p4q5r6
Create Date: 2026-06-24 13:20:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n3o4p5q6r7s8'
down_revision: Union[str, None] = 'a0b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('calibrations', sa.Column('mit_notation', sa.String(length=255), nullable=True))
    op.add_column('calibrations', sa.Column('mi_modification', sa.String(length=255), nullable=True))
    op.add_column('calibrations', sa.Column('applicability', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('calibrations', 'applicability')
    op.drop_column('calibrations', 'mi_modification')
    op.drop_column('calibrations', 'mit_notation')
