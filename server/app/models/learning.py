"""Ôn tập từ giáo trình: lượt làm bài trắc nghiệm và sổ câu sai.

Câu hỏi được sinh từ giáo trình qua `RagClientService.quiz()` — đi qua cùng
ngưỡng τ như hỏi đáp, nên chủ đề không có trong giáo trình thì không sinh câu
nào. Mỗi câu giữ lại tệp nguồn + trang để học viên đối chiếu.

`ReviewItem` là sổ câu sai theo kiểu hộp Leitner: làm sai thì về hộp 1 (ôn lại
sau 1 ngày), làm đúng thì lên một hộp (3, 7, 14 ngày), qua hộp cuối thì coi là
đã thuộc và không đưa ra nữa.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import TIMESTAMPTZ, created_at_col, updated_at_col, uuid_pk


class QuizStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        "course_id", PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    # NULL = lượt ôn câu sai, không sinh câu mới.
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[QuizStatus] = mapped_column(
        SAEnum(QuizStatus, name="QuizStatus", native_enum=True), default=QuizStatus.IN_PROGRESS
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column("submitted_at", TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="QuizQuestion.ordinal"
    )

    __table_args__ = (Index("ix_quiz_sessions_user_id_created_at", "user_id", "created_at"),)


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        "session_id", PGUUID(as_uuid=True), ForeignKey("quiz_sessions.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    correct_index: Mapped[int] = mapped_column("correct_index", Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str | None] = mapped_column("source_file", String, nullable=True)
    source_page: Mapped[int | None] = mapped_column("source_page", Integer, nullable=True)
    selected_index: Mapped[int | None] = mapped_column("selected_index", Integer, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column("is_correct", Boolean, nullable=True)
    # Câu này lấy lại từ sổ câu sai (không phải câu mới sinh).
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(
        "review_item_id", PGUUID(as_uuid=True), ForeignKey("review_items.id", ondelete="SET NULL"), nullable=True
    )

    session: Mapped["QuizSession"] = relationship(back_populates="questions")

    __table_args__ = (UniqueConstraint("session_id", "ordinal", name="uq_quiz_questions_session_ordinal"),)


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        "course_id", PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    # sha256 của nội dung câu hỏi — cùng một câu sai hai lần thì chỉ một dòng.
    question_hash: Mapped[str] = mapped_column("question_hash", String, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    correct_index: Mapped[int] = mapped_column("correct_index", Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str | None] = mapped_column("source_file", String, nullable=True)
    source_page: Mapped[int | None] = mapped_column("source_page", Integer, nullable=True)
    box: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # NULL = đã thuộc, không đưa ra ôn nữa.
    due_at: Mapped[datetime | None] = mapped_column("due_at", TIMESTAMPTZ, nullable=True)
    times_wrong: Mapped[int] = mapped_column("times_wrong", Integer, nullable=False, default=0)
    times_right: Mapped[int] = mapped_column("times_right", Integer, nullable=False, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column("last_reviewed_at", TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("user_id", "question_hash", name="uq_review_items_user_question"),
        Index("ix_review_items_user_id_due_at", "user_id", "due_at"),
    )
