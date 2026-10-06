"""Async SQLAlchemy engine/session setup.

Replaces Prisma. The shared root `.env`'s `DATABASE_URL` is written in Prisma's
dialect (`postgresql://...?schema=public`) — asyncpg doesn't understand the
`schema` query param and needs the `+asyncpg` driver marker, so we normalize it
here rather than asking users to maintain two DSNs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


def to_asyncpg_dsn(raw: str) -> str:
    """Convert a Prisma-style postgresql DSN to an asyncpg-compatible one."""
    parts = urlsplit(raw)
    scheme = parts.scheme
    if scheme in ("postgresql", "postgres"):
        scheme = "postgresql+asyncpg"
    # Drop Prisma-only query params (e.g. schema=public) that asyncpg rejects.
    return urlunsplit((scheme, parts.netloc, parts.path, "", parts.fragment))


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_async_engine(
    to_asyncpg_dsn(_settings.database_url),
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
