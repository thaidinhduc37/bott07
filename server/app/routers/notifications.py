"""Port of the (deleted) NestJS notifications controller — deliberately NO
service class, matching the reference's own choice ("the controller injects
Prisma directly, an indirection layer would only reduce readability"). Two
straight queries, both always scoped by `user_id` from the session — a
foreign notification id in `MarkReadRequest.ids` simply matches zero rows,
not an error (same anti-enumeration shape as everywhere else: no leak about
whether that id belongs to someone else).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db
from app.models.notifications import Notification
from app.schemas.base import CamelModel

router = APIRouter(prefix="/notifications", tags=["notifications"])


class MarkReadRequest(CamelModel):
    ids: list[str] | None = Field(default=None)


@router.get("")
async def list_notifications(
    chua_doc: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if chua_doc:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(50)
    rows = (await db.execute(stmt)).scalars().all()

    unread = (
        await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        )
    ).scalar_one()

    return {
        "items": [
            {
                "id": str(n.id), "type": n.type, "title": n.title, "body": n.body, "linkTo": n.link_to,
                "readAt": n.read_at, "createdAt": n.created_at,
            }
            for n in rows
        ],
        "unread": unread,
    }


@router.patch("/read")
async def mark_read(
    dto: MarkReadRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if dto.ids:
        stmt = stmt.where(Notification.id.in_(dto.ids))
    # Empty/absent ids -> mark ALL of this user's unread notifications read.
    result = await db.execute(stmt.values(read_at=func.now()))
    await db.commit()
    return {"message": "Đã đánh dấu đã đọc", "updated": result.rowcount or 0}
