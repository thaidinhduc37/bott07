"""`AdminDashboardService.get_activity_stats()`: thống kê hoạt động cho trang chủ quản trị. Đặt riêng vì nối hai miền (người dùng và
lịch) nên không thuộc rõ về `users_service.py` hay `schedules_service.py`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from app.models.academic import ExamSchedule, Schedule
from app.models.audit import AuditLog
from app.models.enums import ExamStatus, ScheduleStatus
from app.models.users import Role, User, UserRole

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class AdminDashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_activity_stats(self) -> dict:
        now = datetime.now(timezone.utc)

        active_7d = (
            await self.db.execute(
                select(func.count()).select_from(User).where(User.last_login_at >= now - timedelta(days=7))
            )
        ).scalar_one()
        active_30d = (
            await self.db.execute(
                select(func.count()).select_from(User).where(User.last_login_at >= now - timedelta(days=30))
            )
        ).scalar_one()

        by_role_rows = (
            await self.db.execute(
                select(Role.code, func.count())
                .join(UserRole, UserRole.role_id == Role.id)
                .group_by(Role.code)
            )
        ).all()

        since_7d = now - timedelta(days=7)
        failed_rows = (
            await self.db.execute(
                select(AuditLog.created_at).where(AuditLog.action == "LOGIN_FAILED", AuditLog.created_at >= since_7d)
            )
        ).all()
        by_day: dict[str, int] = {}
        for i in range(7):
            day = (now - timedelta(days=6 - i)).astimezone(VN_TZ).strftime("%Y-%m-%d")
            by_day[day] = 0
        for (created_at,) in failed_rows:
            day = created_at.astimezone(VN_TZ).strftime("%Y-%m-%d")
            if day in by_day:
                by_day[day] += 1
        failed_logins_7d = [{"day": d, "count": c} for d, c in sorted(by_day.items())]

        now_vn = datetime.now(VN_TZ)
        monday = now_vn.date() - timedelta(days=now_vn.weekday())
        week_start = datetime(monday.year, monday.month, monday.day, tzinfo=VN_TZ).astimezone(timezone.utc)
        week_end = week_start + timedelta(days=7)
        schedule_this_week = (
            await self.db.execute(
                select(func.count()).select_from(Schedule).where(
                    Schedule.starts_at >= week_start, Schedule.starts_at < week_end,
                    Schedule.status == ScheduleStatus.SCHEDULED,
                )
            )
        ).scalar_one()

        exams_next_14d = (
            await self.db.execute(
                select(func.count()).select_from(ExamSchedule).where(
                    ExamSchedule.starts_at >= now, ExamSchedule.starts_at < now + timedelta(days=14),
                    ExamSchedule.status == ExamStatus.PUBLISHED,
                )
            )
        ).scalar_one()

        return {
            "activeUsers7d": active_7d,
            "activeUsers30d": active_30d,
            # Mảng {role, count} — đúng kiểu `ActivityAdminStats` phía client (dict làm
            # `usersByRole.map` văng lỗi và sập cả trang chủ quản trị).
            "usersByRole": [{"role": code.value, "count": count} for code, count in by_role_rows],
            "failedLogins7d": failed_logins_7d,
            "scheduleThisWeek": schedule_this_week,
            "examsNext14d": exams_next_14d,
        }
