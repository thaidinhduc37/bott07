"""add chat_feedback

Revision ID: f1d4b8c36a27
Revises: e9c3a7b52d14
Create Date: 2026-10-06 00:00:00.000000

Phản hồi hữu ích / chưa đúng của người dùng về câu trả lời của trợ lý.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1d4b8c36a27'
down_revision: Union[str, None] = 'e9c3a7b52d14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rating', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('comment', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('message_id', 'user_id', name='uq_chat_feedback_message_user'),
    )
    op.create_index('ix_chat_feedback_rating_created_at', 'chat_feedback', ['rating', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_chat_feedback_rating_created_at', table_name='chat_feedback')
    op.drop_table('chat_feedback')
