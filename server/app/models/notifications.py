from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import TIMESTAMPTZ, created_at_col, uuid_pk
from app.models.enums import NotificationType


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="NotificationType", native_enum=True), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link_to: Mapped[str | None] = mapped_column("link_to", String, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column("read_at", TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (Index("ix_notifications_user_id_read_at_created_at", "user_id", "read_at", "created_at"),)
