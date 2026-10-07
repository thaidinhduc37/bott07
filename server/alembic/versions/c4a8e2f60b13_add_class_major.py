"""add classes.major

Revision ID: c4a8e2f60b13
Revises: b3f7d1a52e69
Create Date: 2026-10-07 00:00:00.000000

Ngành / chuyên ngành của lớp. Lớp đã có tên dạng "Lớp B3D15 — An toàn thông tin" được suy ngành từ phần sau dấu "—".
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4a8e2f60b13'
down_revision: Union[str, None] = 'b3f7d1a52e69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('classes', sa.Column('major', sa.String(), nullable=True))
    op.execute(
        "UPDATE classes SET major = NULLIF(btrim(split_part(name, '—', 2)), '') WHERE name LIKE '%—%'"
    )


def downgrade() -> None:
    op.drop_column('classes', 'major')
