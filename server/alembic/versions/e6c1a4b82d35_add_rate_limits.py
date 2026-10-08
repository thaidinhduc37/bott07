"""add rate_limits

Revision ID: e6c1a4b82d35
Revises: d5b9f3a71c24
Create Date: 2026-10-08 00:00:00.000000

Bộ đếm giới hạn tần suất dùng chung giữa các tiến trình API (UNLOGGED: nhanh, mất khi PostgreSQL sập là chấp nhận được).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e6c1a4b82d35'
down_revision: Union[str, None] = 'd5b9f3a71c24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rate_limits',
        sa.Column('bucket', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('window', sa.BigInteger(), nullable=False),
        sa.Column('hits', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('bucket', 'key', 'window'),
        prefixes=['UNLOGGED'],
    )


def downgrade() -> None:
    op.drop_table('rate_limits')
