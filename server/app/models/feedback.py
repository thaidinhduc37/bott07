"""Phản hồi của người dùng về câu trả lời của trợ lý: hữu ích (UP) hay chưa đúng (DOWN, kèm lý do).

Mỗi người một đánh giá cho mỗi câu trả lời (đánh giá lại thì ghi đè). Cán bộ quản lý đào tạo chỉ thấy
câu hỏi, câu trả lời và lý do — KHÔNG thấy ai đã đánh giá (xem `feedback_service.review_list`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import created_at_col, updated_at_col, uuid_pk

RATING_UP = "UP"
RATING_DOWN = "DOWN"
# Lý do khi đánh giá chưa đúng (chuỗi thường để thêm lý do mới không cần migration).
REASONS = {
    "WRONG": "Nội dung sai hoặc lỗi thời",
    "NO_SOURCE": "Thiếu hoặc sai nguồn trích dẫn",
    "IRRELEVANT": "Không đúng câu hỏi",
    "SHOULD_ANSWER": "Đáng lẽ phải trả lời được (trợ lý từ chối)",
    "OTHER": "Lý do khác",
}


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        "message_id", PGUUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_chat_feedback_message_user"),
        Index("ix_chat_feedback_rating_created_at", "rating", "created_at"),
    )
