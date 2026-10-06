"""Phản hồi về câu trả lời của trợ lý.

  * Người dùng chỉ đánh giá được câu trả lời trong hội thoại CỦA MÌNH (người khác → 404, không lộ là có tồn tại).
  * Mỗi người một đánh giá cho mỗi câu; đánh giá lại thì ghi đè, `rating = None` thì xóa.
  * Cán bộ quản lý đào tạo xem danh sách câu bị đánh giá chưa đúng để biết chỗ cần bổ sung tài liệu / chỉnh trợ lý.
    Danh sách này KHÔNG chứa danh tính người đánh giá (cùng nguyên tắc ẩn danh với thống kê giảng viên).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser
from app.models.chat import ChatConversation, ChatMessage
from app.models.enums import MessageRole
from app.models.feedback import RATING_DOWN, RATING_UP, REASONS, ChatFeedback

COMMENT_MAX = 500
WINDOW_DAYS = 30


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"message": "Không tìm thấy câu trả lời"})


class FeedbackService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_feedback(
        self, user: AuthenticatedUser, message_id: str, *, rating: str | None, reason: str | None, comment: str | None
    ) -> dict:
        try:
            mid = uuid.UUID(message_id)
        except (ValueError, TypeError):
            raise _not_found()
        row = (
            await self.db.execute(
                select(ChatMessage, ChatConversation.user_id)
                .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
                .where(ChatMessage.id == mid)
            )
        ).first()
        if row is None or str(row[1]) != str(user.id) or row[0].role != MessageRole.ASSISTANT:
            raise _not_found()

        uid = uuid.UUID(user.id)
        existing = (
            await self.db.execute(select(ChatFeedback).where(ChatFeedback.message_id == mid, ChatFeedback.user_id == uid))
        ).scalar_one_or_none()

        if rating is None:
            if existing is not None:
                await self.db.delete(existing)
                await self.db.commit()
            return {"feedback": None}

        if rating not in (RATING_UP, RATING_DOWN):
            raise HTTPException(status_code=400, detail={"message": "Đánh giá không hợp lệ", "code": "INVALID_RATING"})
        if rating == RATING_DOWN:
            if reason is not None and reason not in REASONS:
                raise HTTPException(status_code=400, detail={"message": "Lý do không hợp lệ", "code": "INVALID_REASON"})
            clean_reason = reason
        else:
            clean_reason = None  # lý do chỉ có nghĩa với "chưa đúng"
        clean_comment = (comment or "").strip()[:COMMENT_MAX] or None
        if rating == RATING_UP:
            clean_comment = None

        if existing is None:
            existing = ChatFeedback(message_id=mid, user_id=uid, rating=rating, reason=clean_reason, comment=clean_comment)
            self.db.add(existing)
        else:
            existing.rating, existing.reason, existing.comment = rating, clean_reason, clean_comment
        await self.db.commit()
        return {"feedback": {"rating": rating, "reason": clean_reason, "comment": clean_comment}}

    async def mine_for(self, user_id: str, message_ids: list[uuid.UUID]) -> dict[str, dict]:
        """Phản hồi của chính người dùng cho một loạt câu trả lời (gắn vào lịch sử hội thoại)."""
        if not message_ids:
            return {}
        rows = (
            await self.db.execute(
                select(ChatFeedback).where(
                    ChatFeedback.user_id == uuid.UUID(user_id), ChatFeedback.message_id.in_(message_ids)
                )
            )
        ).scalars().all()
        return {
            str(f.message_id): {"rating": f.rating, "reason": f.reason, "comment": f.comment} for f in rows
        }

    async def review_list(self, limit: int) -> dict:
        """Tổng hợp 30 ngày và danh sách câu trả lời bị đánh giá chưa đúng (mới nhất trước), không kèm người đánh giá."""
        since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
        counts = {
            rating: n
            for rating, n in (
                await self.db.execute(
                    select(ChatFeedback.rating, func.count()).where(ChatFeedback.created_at >= since).group_by(ChatFeedback.rating)
                )
            ).all()
        }
        by_reason = {
            reason: n
            for reason, n in (
                await self.db.execute(
                    select(ChatFeedback.reason, func.count())
                    .where(ChatFeedback.created_at >= since, ChatFeedback.rating == RATING_DOWN, ChatFeedback.reason.is_not(None))
                    .group_by(ChatFeedback.reason)
                )
            ).all()
        }

        rows = (
            await self.db.execute(
                select(ChatFeedback, ChatMessage, ChatConversation.mode)
                .join(ChatMessage, ChatMessage.id == ChatFeedback.message_id)
                .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
                .where(ChatFeedback.rating == RATING_DOWN, ChatFeedback.created_at >= since)
                .order_by(ChatFeedback.updated_at.desc())
                .limit(limit)
            )
        ).all()

        items = []
        for fb, msg, mode in rows:
            # Câu hỏi = tin của người dùng liền trước câu trả lời trong cùng hội thoại.
            question = (
                await self.db.execute(
                    select(ChatMessage.content)
                    .where(
                        ChatMessage.conversation_id == msg.conversation_id,
                        ChatMessage.role == MessageRole.USER,
                        ChatMessage.created_at <= msg.created_at,
                    )
                    .order_by(ChatMessage.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            items.append(
                {
                    "question": question,
                    "answer": msg.content[:600],
                    "abstained": bool(msg.abstained),
                    "mode": getattr(mode, "value", mode),
                    "confidence": round(msg.confidence, 3) if msg.confidence is not None else None,
                    "reason": fb.reason,
                    "reasonLabel": REASONS.get(fb.reason or "", None),
                    "comment": fb.comment,
                    "createdAt": fb.updated_at,
                }
            )
        up, down = counts.get(RATING_UP, 0), counts.get(RATING_DOWN, 0)
        return {
            "windowDays": WINDOW_DAYS,
            "up": up,
            "down": down,
            "helpfulRate": round(up / (up + down), 3) if (up + down) else None,
            "byReason": [{"reason": r, "label": REASONS.get(r, r), "count": n} for r, n in sorted(by_reason.items(), key=lambda x: -x[1])],
            "items": items,
        }
