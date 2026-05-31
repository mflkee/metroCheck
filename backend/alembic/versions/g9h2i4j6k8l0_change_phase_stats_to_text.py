"""Change phase_stats to text

Revision ID: g9h2i4j6k8l0
Revises: f8a4h6i0k1l2
Create Date: 2026-05-31 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g9h2i4j6k8l0'
down_revision: Union[str, None] = 'f8a4h6i0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('jobs', 'phase_stats',
                    type_=sa.Text(),
                    existing_type=sa.JSON(),
                    postgresql_using='phase_stats::text')


def downgrade() -> None:
    op.alter_column('jobs', 'phase_stats',
                    type_=sa.JSON(),
                    existing_type=sa.Text(),
                    postgresql_using='phase_stats::json')
