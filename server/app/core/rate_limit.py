"""Giới hạn tần suất theo cửa sổ cố định, đếm trong PostgreSQL để mọi tiến trình API dùng chung một bộ đếm.

Lỗi CSDL khi đếm thì cho qua (và ghi cảnh báo): một sự cố bộ đếm không được khóa cả hệ thống.
"""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import AsyncSessionLocal
from app.models.rate_limit import rate_limits

logger = logging.getLogger("rate_limit")

WINDOW_SECONDS = 60
PURGE_EVERY = 500
_calls = 0


async def check(bucket: str, key: str, limit: int) -> None:
    """Tính một lượt cho `(bucket, key)` và trả 429 khi vượt `limit` lượt trong cửa sổ 60 giây hiện tại."""
    global _calls
    window = int(time.time() // WINDOW_SECONDS)
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                insert(rate_limits)
                .values(bucket=bucket, key=key, window=window, hits=1)
                .on_conflict_do_update(
                    index_elements=[rate_limits.c.bucket, rate_limits.c.key, rate_limits.c.window],
                    set_={"hits": rate_limits.c.hits + 1},
                )
                .returning(rate_limits.c.hits)
            )
            hits = (await db.execute(stmt)).scalar_one()
            _calls += 1
            if _calls % PURGE_EVERY == 0:
                await db.execute(delete(rate_limits).where(rate_limits.c.window < window - 5))
            await db.commit()
    except SQLAlchemyError:
        logger.warning("Không đếm được giới hạn tần suất (%s), cho qua", bucket, exc_info=True)
        return
    if hits > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "Quá nhiều yêu cầu, vui lòng thử lại sau", "code": "RATE_LIMITED"},
        )
