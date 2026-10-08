"""Bộ đếm giới hạn tần suất dùng chung giữa các tiến trình API (bảng UNLOGGED: mất khi PostgreSQL sập là chấp nhận được)."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Integer, PrimaryKeyConstraint, String, Table

from app.core.db import Base

rate_limits = Table(
    "rate_limits",
    Base.metadata,
    Column("bucket", String, nullable=False),
    Column("key", String, nullable=False),
    Column("window", BigInteger, nullable=False),
    Column("hits", Integer, nullable=False, server_default="0"),
    PrimaryKeyConstraint("bucket", "key", "window"),
    prefixes=["UNLOGGED"],
)
