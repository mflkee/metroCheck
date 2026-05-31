"""Merge alembic heads

Revision ID: j2k4l6m8n0p2
Revises: e7f3g5h8i9j0, h1i3j5k7l9m1
Create Date: 2026-05-31 06:50:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'j2k4l6m8n0p2'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = ('e7f3g5h8i9j0', 'h1i3j5k7l9m1')


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
