"""Merge heads

Revision ID: f8a4h6i0k1l2
Revises: 3a9de0aad3b0, e7f3g5h8i9j0
Create Date: 2026-05-31 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8a4h6i0k1l2'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = ('3a9de0aad3b0', 'e7f3g5h8i9j0')


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
