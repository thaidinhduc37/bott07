"""Nhắc ôn tập: tạo thông báo trong ứng dụng cho học viên.

Hai loại nhắc:
  * Có câu trong sổ câu sai đã đến hạn ôn — tối đa một lần mỗi ngày (giờ VN).
  * Kỳ thi của lớp còn đúng 7, 3 hoặc 1 ngày — mỗi mốc một lần.

Chạy lặp trong tiến trình API (`start()` gọi ở startup), mỗi `INTERVAL_S`
giây. Mỗi lượt đều idempotent — chạy lại bao nhiêu lần trong ngày cũng không
sinh thông báo trùng — nên khởi động lại API hay chạy nhiều bản cùng lúc không
làm học viên bị gửi dồn.

Tắt bằng biến môi trường `STUDY_REMINDERS=0`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import ExamSchedule
from app.models.enums import ExamStatus, NotificationType
from app.models.learning import ReviewItem
from app.models.notifications import Notification
from app.models.users import StudentProfile

logger = logging.getLogger("study_reminders")

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
EXAM_MILESTONES = (7, 3, 1)
INTERVAL_S = 3600
REVIEW_LINK = "/sinh-vien/on-tap/so-cau-sai"


def _vn_day_start_utc(now: datetime) -> datetime:
    local = now.astimezone(VN_TZ)
    return datetime.combine(local.date(), time.min, tzinfo=VN_TZ).astimezone(timezone.utc)


async def remind_review_due(db: AsyncSession, now: datetime) -> int:
    rows = (
        await db.execute(
            select(ReviewItem.user_id, func.count().label("due"))
            .where(ReviewItem.due_at.is_not(None), ReviewItem.due_at <= now)
            .group_by(ReviewItem.user_id)
        )
    ).all()
    if not rows:
        return 0
    already = set(
        (
            await db.execute(
                select(Notification.user_id).where(
                    Notification.link_to == REVIEW_LINK,
                    Notification.created_at >= _vn_day_start_utc(now),
                    Notification.user_id.in_([r.user_id for r in rows]),
                )
            )
        ).scalars().all()
    )
    created = 0
    for r in rows:
        if r.user_id in already:
            continue
        db.add(
            Notification(
                user_id=r.user_id,
                type=NotificationType.SYSTEM,
                title=f"Có {r.due} câu cần ôn lại hôm nay",
                body="Các câu bạn từng làm sai đã đến hạn ôn. Ôn đúng hạn giúp nhớ lâu hơn nhiều so với ôn dồn trước kỳ thi.",
                link_to=REVIEW_LINK,
                # Mốc chống trùng tính theo `now` truyền vào, nên thời điểm tạo cũng phải là `now`.
                created_at=now,
            )
        )
        created += 1
    return created


async def remind_exams(db: AsyncSession, now: datetime) -> int:
    today = now.astimezone(VN_TZ).date()
    created = 0
    for days in EXAM_MILESTONES:
        day = today + timedelta(days=days)
        start = datetime.combine(day, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
        exams = (
            await db.execute(
                select(ExamSchedule)
                .where(
                    ExamSchedule.status == ExamStatus.PUBLISHED,
                    ExamSchedule.starts_at >= start,
                    ExamSchedule.starts_at < start + timedelta(days=1),
                )
            )
        ).scalars().all()
        for exam in exams:
            await db.refresh(exam, ["course"])
            # Kế hoạch ôn thi nay là tab của trang Ôn tập. Thông báo đã gửi trước đó dùng
            # địa chỉ cũ (/sinh-vien/ke-hoach-on-thi#…, vẫn chuyển hướng được); khi dò
            # "đã gửi chưa" phải nhận cả hai, không thì mỗi mốc sẽ bị gửi lại một lần.
            link = f"/sinh-vien/on-tap?tab=ke-hoach#{exam.id}"
            legacy_link = f"/sinh-vien/ke-hoach-on-thi#{exam.id}"
            title = f"Còn {days} ngày tới kỳ thi {exam.course.code}"
            students = (
                await db.execute(select(StudentProfile.user_id).where(StudentProfile.class_id == exam.class_id))
            ).scalars().all()
            if not students:
                continue
            already = set(
                (
                    await db.execute(
                        select(Notification.user_id).where(
                            Notification.link_to.in_([link, legacy_link]),
                            Notification.title == title,
                            Notification.user_id.in_(students),
                        )
                    )
                ).scalars().all()
            )
            when = exam.starts_at.astimezone(VN_TZ)
            for uid in students:
                if uid in already:
                    continue
                db.add(
                    Notification(
                        user_id=uid,
                        type=NotificationType.SYSTEM,
                        title=title,
                        body=(
                            f"{exam.course.name}: thi ngày {when:%d/%m} lúc {when:%H:%M}, phòng {exam.room}. "
                            "Xem kế hoạch ôn thi để biết nên ôn gì mỗi ngày."
                        ),
                        link_to=link,
                        created_at=now,
                    )
                )
                created += 1
    return created


async def run_once(db: AsyncSession, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    review = await remind_review_due(db, now)
    exams = await remind_exams(db, now)
    await db.commit()
    return {"review": review, "exams": exams}


_task: asyncio.Task | None = None


async def _loop() -> None:
    from app.core.db import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await run_once(db)
            if result["review"] or result["exams"]:
                logger.info("Đã tạo thông báo nhắc ôn: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:  # một lượt lỗi không được làm chết vòng lặp
            logger.exception("Lượt nhắc ôn tập lỗi")
        await asyncio.sleep(INTERVAL_S)


def start() -> None:
    global _task
    if os.getenv("STUDY_REMINDERS", "1") == "0":
        logger.info("Nhắc ôn tập đang tắt (STUDY_REMINDERS=0)")
        return
    if _task is None:
        _task = asyncio.get_running_loop().create_task(_loop())


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
