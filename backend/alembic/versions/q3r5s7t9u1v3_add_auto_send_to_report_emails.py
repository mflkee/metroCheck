"""add auto_send to report_emails

Revision ID: q3r5s7t9u1v3
Revises: p2q4r6s8t0u2
Create Date: 2026-10-14 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q3r5s7t9u1v3'
down_revision: Union[str, None] = 'p2q4r6s8t0u2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Персональный флаг автоотправки: письмо после проверки уходит только тем,
    # у кого он включён.
    op.add_column(
        'report_emails',
        sa.Column('auto_send', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('report_emails', 'auto_send')
