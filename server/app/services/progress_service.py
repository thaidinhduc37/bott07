"""Tiến trình ôn tập của chính học viên — số liệu cho trang chủ.

Chỉ đọc dữ liệu của `user_id` truyền vào (lượt làm bài đã nộp + sổ câu sai), không
có gì liên quan tới người khác nên không cần ngưỡng ẩn danh như `insights_service`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import Course
from app.models.learning import QuizSession, QuizStatus, ReviewItem

ACTIVITY_DAYS = 14
WEEK_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProgressService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def overview(self, user_id: uuid.UUID | str) -> dict:
        now = _now()
        since = now - timedelta(days=ACTIVITY_DAYS - 1)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)

        sessions = (
            await self.db.execute(
                select(QuizSession)
                .where(
                    QuizSession.user_id == user_id,
                    QuizSession.status == QuizStatus.SUBMITTED,
                    QuizSession.submitted_at.is_not(None),
                )
                .order_by(QuizSession.submitted_at.desc())
                .limit(500)
            )
        ).scalars().all()

        # Ngày theo giờ địa phương của máy chủ = ngày học viên nhìn thấy trên lịch.
        def day_of(dt: datetime) -> date:
            return dt.astimezone().date()

        today = now.astimezone().date()
        by_day: dict[date, int] = {}
        for s in sessions:
            d = day_of(s.submitted_at)
            by_day[d] = by_day.get(d, 0) + 1

        activity = [
            {"date": (today - timedelta(days=i)).isoformat(), "count": by_day.get(today - timedelta(days=i), 0)}
            for i in range(ACTIVITY_DAYS - 1, -1, -1)
        ]

        # Chuỗi ngày liên tiếp có ôn. Hôm nay chưa ôn thì chuỗi vẫn tính từ hôm qua,
        # để đầu ngày không bị hiện "0 ngày" khi học viên chưa kịp làm.
        streak = 0
        cursor = today if by_day.get(today) else today - timedelta(days=1)
        while by_day.get(cursor):
            streak += 1
            cursor -= timedelta(days=1)

        week_from = today - timedelta(days=WEEK_DAYS - 1)
        week = [s for s in sessions if day_of(s.submitted_at) >= week_from]
        scored = [s.score for s in week if s.score is not None]

        # Theo môn: số lượt, điểm TB, điểm lượt gần nhất (tính trên toàn bộ lượt đã nộp).
        per_course: dict[uuid.UUID, dict] = {}
        for s in sessions:
            if s.course_id is None:
                continue
            c = per_course.setdefault(s.course_id, {"scores": [], "sessions": 0, "last": None})
            c["sessions"] += 1
            if s.score is not None:
                c["scores"].append(s.score)
                if c["last"] is None:  # `sessions` đã sắp mới nhất trước
                    c["last"] = s.score

        review_rows = (
            await self.db.execute(
                select(
                    ReviewItem.course_id,
                    func.count().filter(ReviewItem.due_at.is_not(None), ReviewItem.due_at <= now).label("due"),
                    func.count().filter(ReviewItem.due_at.is_(None)).label("mastered"),
                    func.count().label("total"),
                )
                .where(ReviewItem.user_id == user_id)
                .group_by(ReviewItem.course_id)
            )
        ).all()
        review = {r.course_id: r for r in review_rows}

        ids = {c for c in per_course} | {c for c in review if c is not None}
        courses = {}
        if ids:
            courses = {
                c.id: c for c in (await self.db.execute(select(Course).where(Course.id.in_(ids)))).scalars().all()
            }

        items = []
        for cid in ids:
            course = courses.get(cid)
            if not course:
                continue
            c = per_course.get(cid)
            r = review.get(cid)
            items.append(
                {
                    "course": {"id": str(course.id), "code": course.code, "name": course.name},
                    "sessions": c["sessions"] if c else 0,
                    "avgScore": round(sum(c["scores"]) / len(c["scores"]), 1) if c and c["scores"] else None,
                    "lastScore": c["last"] if c else None,
                    "reviewDue": r.due if r else 0,
                    "mastered": r.mastered if r else 0,
                    "wrongTotal": r.total if r else 0,
                }
            )
        # Môn cần chú ý lên đầu: nhiều câu đến hạn, rồi điểm thấp.
        items.sort(key=lambda x: (-x["reviewDue"], x["avgScore"] if x["avgScore"] is not None else 101))

        totals = (
            await self.db.execute(
                select(
                    func.count().filter(ReviewItem.due_at.is_not(None), ReviewItem.due_at <= now).label("due"),
                    func.count().filter(ReviewItem.due_at.is_(None)).label("mastered"),
                    func.count().filter(ReviewItem.due_at.is_not(None)).label("learning"),
                ).where(ReviewItem.user_id == user_id)
            )
        ).one()

        return {
            "week": {
                "sessions": len(week),
                "avgScore": round(sum(scored) / len(scored), 1) if scored else None,
            },
            "streakDays": streak,
            "totalSessions": len(sessions),
            "activity": activity,
            "review": {"due": totals.due, "learning": totals.learning, "mastered": totals.mastered},
            "courses": items,
        }
