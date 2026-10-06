"""add course_grades

Revision ID: e9c3a7b52d14
Revises: d8b2f4a61c93
Create Date: 2026-10-06 00:00:00.000000

Điểm học phần: một dòng cho mỗi (học viên, môn, năm học, học kỳ).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e9c3a7b52d14'
down_revision: Union[str, None] = 'd8b2f4a61c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'course_grades',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('academic_year', sa.String(), nullable=False),
        sa.Column('semester', sa.String(), nullable=False),
        sa.Column('practice', sa.Float(), nullable=True),
        sa.Column('process', sa.Float(), nullable=True),
        sa.Column('midterm', sa.Float(), nullable=True),
        sa.Column('final_exam', sa.Float(), nullable=True),
        sa.Column('total', sa.Float(), nullable=True),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('student_id', 'course_id', 'academic_year', 'semester', name='uq_course_grades_unique'),
    )
    op.create_index('ix_course_grades_student_id', 'course_grades', ['student_id'])
    op.create_index('ix_course_grades_course_term', 'course_grades', ['course_id', 'academic_year', 'semester'])


def downgrade() -> None:
    op.drop_index('ix_course_grades_course_term', table_name='course_grades')
    op.drop_index('ix_course_grades_student_id', table_name='course_grades')
    op.drop_table('course_grades')
