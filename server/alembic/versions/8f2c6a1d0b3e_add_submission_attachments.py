"""add submission_attachments table

Revision ID: 8f2c6a1d0b3e
Revises: 41a91c4da0e0
Create Date: 2026-08-26 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8f2c6a1d0b3e'
down_revision: Union[str, None] = '41a91c4da0e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'submission_attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('uploaded_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], ['form_submissions.id'], name='submission_attachments_submission_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], name='submission_attachments_uploaded_by_id_fkey', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='submission_attachments_pkey'),
    )
    op.create_index('ix_submission_attachments_submission_id', 'submission_attachments', ['submission_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_submission_attachments_submission_id', table_name='submission_attachments')
    op.drop_table('submission_attachments')
