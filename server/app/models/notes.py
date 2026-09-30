"""Sổ tay học tập: học viên lưu lại câu trả lời hỏi đáp (kèm trích dẫn), câu
trắc nghiệm đã làm, hoặc ghi chú tự viết — cùng ghi chú riêng của mình.

Nội dung và trích dẫn được CHÉP vào ghi chú (không chỉ tham chiếu id): xóa hội
thoại hay lượt ôn tập thì ghi chú vẫn còn nguyên, giống `ChatCitation` không
khóa ngoại tới tài liệu.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at_col, updated_at_col, uuid_pk

# Nguồn của ghi chú. Chuỗi thường thay vì enum Postgres: thêm nguồn mới không cần migration đổi kiểu.
NOTE_SOURCE_CHAT = "CHAT"
NOTE_SOURCE_QUIZ = "QUIZ"
NOTE_SOURCE_MANUAL = "MANUAL"


class StudyNote(Base):
    __tablename__ = "study_notes"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        "course_id", PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[str] = mapped_column("source_type", String, nullable=False)
    # id tin nhắn / câu hỏi gốc — chỉ để chống lưu trùng, không khóa ngoại.
    source_id: Mapped[uuid.UUID | None] = mapped_column("source_id", PGUUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_study_notes_user_source"),
        Index("ix_study_notes_user_id_updated_at", "user_id", "updated_at"),
    )
