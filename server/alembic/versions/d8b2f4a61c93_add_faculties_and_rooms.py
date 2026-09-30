"""add faculties and rooms

Revision ID: d8b2f4a61c93
Revises: c5a9d2e7f310
Create Date: 2026-09-30 00:00:00.000000

Khoa thành thực thể (trước đây chỉ là chuỗi `classes.faculty`) và danh mục phòng.
Dữ liệu sẵn có được chuyển sang: mỗi tên khoa khác nhau trong `classes.faculty` thành một
dòng `faculties`; mỗi cặp (phòng, tòa) khác nhau trong lịch học/lịch thi thành một dòng `rooms`.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd8b2f4a61c93'
down_revision: Union[str, None] = 'c5a9d2e7f310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'faculties',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(), nullable=False, unique=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('head_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['head_id'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_table(
        'rooms',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('building', sa.String(), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(), nullable=True),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    # (phòng, tòa) không phân biệt hoa thường; tòa NULL coi như chuỗi rỗng.
    op.execute("CREATE UNIQUE INDEX uq_rooms_code_building ON rooms (lower(code), lower(coalesce(building, '')))")

    for table in ('classes', 'courses', 'users'):
        op.add_column(table, sa.Column('faculty_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f'{table}_faculty_id_fkey', table, 'faculties', ['faculty_id'], ['id'], ondelete='SET NULL')
        op.create_index(f'ix_{table}_faculty_id', table, ['faculty_id'])

    # Chuyển tên khoa dạng chữ thành thực thể. Mã tạm sinh từ tên, quản trị đổi lại sau.
    op.execute(
        """
        INSERT INTO faculties (code, name)
        SELECT 'K' || substr(md5(name), 1, 6), name
        FROM (SELECT DISTINCT btrim(faculty) AS name FROM classes WHERE faculty IS NOT NULL AND btrim(faculty) <> '') t
        """
    )
    op.execute("UPDATE classes c SET faculty_id = f.id FROM faculties f WHERE btrim(c.faculty) = f.name")

    # Chuyển các phòng đang dùng vào danh mục (bỏ rỗng / "chưa xếp").
    op.execute(
        """
        INSERT INTO rooms (code, building)
        SELECT DISTINCT ON (lower(btrim(room)), lower(coalesce(btrim(building), '')))
               btrim(room), nullif(btrim(building), '')
        FROM (
            SELECT room, building FROM schedules
            UNION ALL
            SELECT room, building FROM exam_schedules
        ) r
        WHERE btrim(room) <> '' AND lower(btrim(room)) NOT LIKE 'chưa xếp%' AND lower(btrim(room)) NOT LIKE 'chua xep%'
        """
    )


def downgrade() -> None:
    for table in ('users', 'courses', 'classes'):
        op.drop_index(f'ix_{table}_faculty_id', table_name=table)
        op.drop_constraint(f'{table}_faculty_id_fkey', table, type_='foreignkey')
        op.drop_column(table, 'faculty_id')
    op.execute("DROP INDEX IF EXISTS uq_rooms_code_building")
    op.drop_table('rooms')
    op.drop_table('faculties')
