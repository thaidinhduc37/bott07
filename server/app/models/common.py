"""Shared column helpers so every model file uses the same PK/timestamp shape."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def uuid_fk(nullable: bool = False) -> Mapped:
    return mapped_column(PGUUID(as_uuid=True), nullable=nullable)


TIMESTAMPTZ = DateTime(timezone=True)


def created_at_col():
    from sqlalchemy import func

    return mapped_column(TIMESTAMPTZ, server_default=func.now(), nullable=False)


def updated_at_col():
    from sqlalchemy import func

    return mapped_column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now(), nullable=False)
