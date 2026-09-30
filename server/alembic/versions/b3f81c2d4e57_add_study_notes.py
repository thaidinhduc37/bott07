"""add study_notes

Revision ID: b3f81c2d4e57
Revises: a7d3e5b91c20
Create Date: 2026-09-29 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3f81c2d4e57'
down_revision: Union[str, None] = 'a7d3e5b91c20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'study_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        # NULL source_id (ghi chú tự viết) không vướng ràng buộc — Postgres coi NULL là khác nhau.
        sa.UniqueConstraint('user_id', 'source_type', 'source_id', name='uq_study_notes_user_source'),
    )
    op.create_index('ix_study_notes_user_id_updated_at', 'study_notes', ['user_id', 'updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_study_notes_user_id_updated_at', table_name='study_notes')
    op.drop_table('study_notes')
