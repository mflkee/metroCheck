"""add token_alert_sent to jobs

Revision ID: 07002a2b1f9a
Revises: n3o4p5q6r7s8
Create Date: 2026-07-09 14:50:07.755108

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07002a2b1f9a'
down_revision: Union[str, None] = 'n3o4p5q6r7s8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('token_alert_sent', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'token_alert_sent')
