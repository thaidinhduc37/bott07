"""Engine và phiên SQLAlchemy bất đồng bộ. `DATABASE_URL` viết dạng `postgresql://…?schema=public` nên được chuẩn hóa sang
`postgresql+asyncpg://` và bỏ tham số `schema` mà asyncpg không hiểu."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


def to_asyncpg_dsn(raw: str) -> str:
    """Đổi DSN dạng `postgresql://` sang dạng asyncpg."""
    parts = urlsplit(raw)
    scheme = parts.scheme
    if scheme in ("postgresql", "postgres"):
        scheme = "postgresql+asyncpg"
    # Bỏ tham số truy vấn (vd schema=public) mà asyncpg từ chối.
    return urlunsplit((scheme, parts.netloc, parts.path, "", parts.fragment))


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_async_engine(
    to_asyncpg_dsn(_settings.database_url),
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
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
