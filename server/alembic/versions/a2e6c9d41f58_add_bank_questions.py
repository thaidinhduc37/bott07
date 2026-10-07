"""add bank_questions

Revision ID: a2e6c9d41f58
Revises: f1d4b8c36a27
Create Date: 2026-10-07 00:00:00.000000

Ngân hàng câu hỏi trắc nghiệm do giảng viên nhập cho từng môn.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a2e6c9d41f58'
down_revision: Union[str, None] = 'f1d4b8c36a27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bank_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB(), nullable=False),
        sa.Column('correct_index', sa.Integer(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('chapter', sa.String(), nullable=True),
        sa.Column('question_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('course_id', 'question_hash', name='uq_bank_questions_course_question'),
    )
    op.create_index('ix_bank_questions_course_id', 'bank_questions', ['course_id'])


def downgrade() -> None:
    op.drop_index('ix_bank_questions_course_id', table_name='bank_questions')
    op.drop_table('bank_questions')
