"""multi answer questions

Revision ID: b3f7d1a52e69
Revises: a2e6c9d41f58
Create Date: 2026-10-07 00:00:00.000000

Câu trắc nghiệm có nhiều đáp án đúng: `correct_set` (các chỉ số đúng) ở ngân hàng câu hỏi, câu trong bài làm và
sổ câu sai; `selected_set` (các ô đã tick) ở câu trong bài làm. NULL = một đáp án đúng như cũ.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3f7d1a52e69'
down_revision: Union[str, None] = 'a2e6c9d41f58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ('bank_questions', 'quiz_questions', 'review_items')


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column('correct_set', postgresql.JSONB(), nullable=True))
    op.add_column('quiz_questions', sa.Column('selected_set', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('quiz_questions', 'selected_set')
    for table in reversed(_TABLES):
        op.drop_column(table, 'correct_set')
