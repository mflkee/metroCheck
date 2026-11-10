"""Add arshin_mods (справочник модификаций)

Revision ID: r5t7u9v1w3x5
Revises: r4s6t8u0v2w4
Create Date: 2026-11-10 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'r5t7u9v1w3x5'
down_revision: Union[str, None] = 'r4s6t8u0v2w4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'arshin_mods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ot', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_arshin_mods_ot', 'arshin_mods', ['ot'])


def downgrade() -> None:
    op.drop_index('ix_arshin_mods_ot', table_name='arshin_mods')
    op.drop_table('arshin_mods')
