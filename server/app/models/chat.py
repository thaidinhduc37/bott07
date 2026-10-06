from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import created_at_col, updated_at_col, uuid_pk
from app.models.enums import ChatMode, MessageRole


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    mode: Mapped[ChatMode] = mapped_column(
        SAEnum(ChatMode, name="ChatMode", native_enum=True), default=ChatMode.QUYCHE
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_chat_conversations_user_id_updated_at", "user_id", "updated_at"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        "conversation_id",
        PGUUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole, name="MessageRole", native_enum=True))
    content: Mapped[str] = mapped_column(Text, nullable=False)

    abstained: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    grounded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    route: Mapped[str | None] = mapped_column(String, nullable=True)
    rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column("latency_ms", Integer, nullable=True)
    trace: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    retrieved_chunks: Mapped[list | None] = mapped_column("retrieved_chunks", JSONB, nullable=True)

    created_at: Mapped[datetime] = created_at_col()

    conversation: Mapped["ChatConversation"] = relationship(back_populates="messages")
    citations: Mapped[list["ChatCitation"]] = relationship(
        back_populates="message_ref", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_chat_messages_conversation_id_created_at", "conversation_id", "created_at"),)


class ChatCitation(Base):
    __tablename__ = "chat_citations"

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        "message_id", PGUUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    marker: Mapped[int] = mapped_column(Integer, nullable=False)
    # No FK on purpose (see notes): citations must stay readable even if the
    # source document is later deleted.
    document_id: Mapped[uuid.UUID | None] = mapped_column("document_id", PGUUID(as_uuid=True), nullable=True)
    document_title: Mapped[str] = mapped_column("document_title", String, nullable=False)
    source_file: Mapped[str] = mapped_column("source_file", String, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    article_number: Mapped[str | None] = mapped_column("article_number", String, nullable=True)
    rerank_score: Mapped[float | None] = mapped_column("rerank_score", Float, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    message_ref: Mapped["ChatMessage"] = relationship(back_populates="citations")

    __table_args__ = (Index("ix_chat_citations_message_id", "message_id"),)
