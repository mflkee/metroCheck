"""merge_all_heads

Revision ID: 0278a83f8140
Revises: 3a9de0aad3b0, h1i3j5k7l9m1
Create Date: 2026-05-31 06:16:11.974049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0278a83f8140'
down_revision: Union[str, None] = 'h1i3j5k7l9m1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
