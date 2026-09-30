"""add lecturer_note to schedules and exam_schedules

Revision ID: c5a9d2e7f310
Revises: b3f81c2d4e57
Create Date: 2026-09-29 00:00:00.000000

Ghi chú/yêu cầu của giảng viên cho từng buổi học và ca thi — cột riêng, không
dùng chung `note` (cột đó bị ghi đè mỗi lần nạp lại CSV).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5a9d2e7f310'
down_revision: Union[str, None] = 'b3f81c2d4e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('schedules', 'exam_schedules')


def upgrade() -> None:
    for t in TABLES:
        op.add_column(t, sa.Column('lecturer_note', sa.Text(), nullable=True))
        op.add_column(t, sa.Column('lecturer_note_updated_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column(t, sa.Column('lecturer_note_by_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f'{t}_lecturer_note_by_id_fkey', t, 'users', ['lecturer_note_by_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    for t in TABLES:
        op.drop_constraint(f'{t}_lecturer_note_by_id_fkey', t, type_='foreignkey')
        op.drop_column(t, 'lecturer_note_by_id')
        op.drop_column(t, 'lecturer_note_updated_at')
        op.drop_column(t, 'lecturer_note')
