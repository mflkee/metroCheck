"""Add precheck tables (перед АРШИНом)

Revision ID: r4s6t8u0v2w4
Revises: q3r5s7t9u1v3
Create Date: 2026-11-09 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'r4s6t8u0v2w4'
down_revision: str | None = 'q3r5s7t9u1v3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'arshin_types',
        sa.Column('ot', sa.String(length=32), nullable=False),
        sa.Column('mit_uuid', sa.String(length=64), nullable=True),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('notation', sa.String(length=512), nullable=True),
        sa.Column('valid_to', sa.String(length=16), nullable=True),
        sa.Column('spec_url', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('ot'),
    )
    op.create_table(
        'arshin_mpi',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ot', sa.String(length=32), nullable=False),
        sa.Column('months', sa.Integer(), nullable=True),
        sa.Column('parameter', sa.Text(), nullable=True),
        sa.Column('valid_from', sa.String(length=16), nullable=True),
        sa.Column('valid_to', sa.String(length=16), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_arshin_mpi_ot', 'arshin_mpi', ['ot'])
    op.create_table(
        'arshin_meth',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ot', sa.String(length=32), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('dec_num', sa.String(length=128), nullable=True),
        sa.Column('valid_from', sa.String(length=16), nullable=True),
        sa.Column('valid_to', sa.String(length=16), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_arshin_meth_ot', 'arshin_meth', ['ot'])
    op.create_table(
        'precheck_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('user', sa.String(length=255), nullable=True),
        sa.Column('profile', sa.String(length=16), nullable=False),
        sa.Column('files', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rows', sa.Integer(), nullable=False),
        sa.Column('errors', sa.Integer(), nullable=False),
        sa.Column('warnings', sa.Integer(), nullable=False),
        sa.Column('report_path', sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_precheck_runs_created_at', 'precheck_runs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_precheck_runs_created_at', table_name='precheck_runs')
    op.drop_table('precheck_runs')
    op.drop_index('ix_arshin_meth_ot', table_name='arshin_meth')
    op.drop_table('arshin_meth')
    op.drop_index('ix_arshin_mpi_ot', table_name='arshin_mpi')
    op.drop_table('arshin_mpi')
    op.drop_table('arshin_types')
