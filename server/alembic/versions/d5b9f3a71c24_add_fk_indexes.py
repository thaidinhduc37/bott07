"""add fk indexes

Revision ID: d5b9f3a71c24
Revises: c4a8e2f60b13
Create Date: 2026-10-08 00:00:00.000000

Chỉ mục cho các khóa ngoại được lọc thường xuyên: phạm vi giảng viên (`courses.lecturer_id`), lọc người dùng theo vai trò,
thống kê theo môn của giảng viên.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = 'd5b9f3a71c24'
down_revision: Union[str, None] = 'c4a8e2f60b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = [
    ('ix_courses_lecturer_id', 'courses', ['lecturer_id']),
    ('ix_user_roles_role_id', 'user_roles', ['role_id']),
    ('ix_quiz_sessions_course_id', 'quiz_sessions', ['course_id']),
    ('ix_review_items_course_id', 'review_items', ['course_id']),
    ('ix_exam_schedules_course_id', 'exam_schedules', ['course_id']),
    ('ix_documents_course_id', 'documents', ['course_id']),
    ('ix_study_notes_course_id', 'study_notes', ['course_id']),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
