"""add learning: quiz_sessions, quiz_questions, review_items

Revision ID: a7d3e5b91c20
Revises: 8f2c6a1d0b3e
Create Date: 2026-09-29 00:00:00.000000

Mở lại chức năng ôn tập từ giáo trình. Hai bảng quiz_* từng bị xóa ở
4184d91af082 nhưng kiểu enum "QuizStatus" vẫn còn trong Postgres (migration đó
không xóa kiểu) — nên kiểu được tạo với checkfirst, bảng thì khai báo
create_type=False để không tạo lần hai.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7d3e5b91c20'
down_revision: Union[str, None] = '8f2c6a1d0b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

quiz_status = postgresql.ENUM('IN_PROGRESS', 'SUBMITTED', name='QuizStatus', create_type=False)


def upgrade() -> None:
    quiz_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'review_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('question_hash', sa.String(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('correct_index', sa.Integer(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('source_file', sa.String(), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('box', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('times_wrong', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_right', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'question_hash', name='uq_review_items_user_question'),
    )
    op.create_index('ix_review_items_user_id_due_at', 'review_items', ['user_id', 'due_at'], unique=False)

    op.create_table(
        'quiz_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('topic', sa.String(), nullable=True),
        sa.Column('status', quiz_status, nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_quiz_sessions_user_id_created_at', 'quiz_sessions', ['user_id', 'created_at'], unique=False)

    op.create_table(
        'quiz_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('correct_index', sa.Integer(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('source_file', sa.String(), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('selected_index', sa.Integer(), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=True),
        sa.Column('review_item_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['quiz_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['review_item_id'], ['review_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'ordinal', name='uq_quiz_questions_session_ordinal'),
    )


def downgrade() -> None:
    op.drop_table('quiz_questions')
    op.drop_index('ix_quiz_sessions_user_id_created_at', table_name='quiz_sessions')
    op.drop_table('quiz_sessions')
    op.drop_index('ix_review_items_user_id_due_at', table_name='review_items')
    op.drop_table('review_items')
    # Giữ kiểu "QuizStatus": nó có từ trước migration này (xem docstring).
