"""Thống kê biểu mẫu cho quản trị."""


from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.enums import SubmissionStatus
from app.models.forms import (
    FormSubmission,
    FormTemplate,
)


class StatsMixin:
    # ------------------------------------------------------- admin stats

    async def get_admin_stats(self) -> dict:
        """Số liệu đơn cho trang chủ quản trị — đúng kiểu `FormsAdminStats` phía client
        (mảng thay vì dict, thời gian xử lý tính theo NGÀY, kèm chuỗi xu hướng 14 ngày)."""
        now = datetime.now(timezone.utc)
        by_status_rows = (
            await self.db.execute(select(FormSubmission.status, func.count()).group_by(FormSubmission.status))
        ).all()
        by_template_rows = (
            await self.db.execute(
                select(FormTemplate.name, func.count())
                .join(FormSubmission, FormSubmission.template_id == FormTemplate.id)
                .group_by(FormTemplate.name)
                .order_by(func.count().desc())
            )
        ).all()

        completed_rows = (
            await self.db.execute(
                select(FormSubmission.submitted_at, FormSubmission.completed_at).where(
                    FormSubmission.status == SubmissionStatus.COMPLETED,
                    FormSubmission.completed_at.is_not(None),
                    FormSubmission.submitted_at.is_not(None),
                )
            )
        ).all()
        avg_turnaround_days = (
            sum((c - s).total_seconds() for s, c in completed_rows) / len(completed_rows) / 86400
            if completed_rows else None
        )

        # Xu hướng 14 ngày gần nhất: ngày không có dữ liệu để `None` (biểu đồ bỏ trống điểm đó).
        days = [(now - timedelta(days=13 - i)).date() for i in range(14)]
        turnaround_by_day: dict[date, list[float]] = {}
        for s_at, c_at in completed_rows:
            turnaround_by_day.setdefault(c_at.date(), []).append((c_at - s_at).total_seconds() / 86400)
        avg_turnaround_trend = [
            {"day": d.isoformat(),
             "value": (sum(turnaround_by_day[d]) / len(turnaround_by_day[d])) if d in turnaround_by_day else None}
            for d in days
        ]

        decided_statuses = (SubmissionStatus.REJECTED, SubmissionStatus.APPROVED, SubmissionStatus.COMPLETED)
        recent = (
            await self.db.execute(
                select(FormSubmission.status, FormSubmission.updated_at).where(
                    FormSubmission.updated_at >= now - timedelta(days=30),
                    FormSubmission.status.in_(decided_statuses),
                )
            )
        ).all()
        rejection_rate = (
            sum(1 for st, _ in recent if st == SubmissionStatus.REJECTED) / len(recent) if recent else None
        )
        decided_by_day: dict[date, list[SubmissionStatus]] = {}
        for st, upd in recent:
            decided_by_day.setdefault(upd.date(), []).append(st)
        rejection_trend = [
            {"day": d.isoformat(),
             "value": (sum(1 for st in decided_by_day[d] if st == SubmissionStatus.REJECTED) / len(decided_by_day[d]))
             if d in decided_by_day else None}
            for d in days
        ]

        backlog_rows = (
            await self.db.execute(
                select(FormSubmission)
                .options(selectinload(FormSubmission.template))
                .where(FormSubmission.status.in_([
                    SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW, SubmissionStatus.NEEDS_REVISION,
                ]))
                .order_by(FormSubmission.submitted_at.asc())
                .limit(10)
            )
        ).scalars().all()

        return {
            "byStatus": [{"status": st.value, "count": n} for st, n in by_status_rows],
            "byTemplate": [{"templateName": name, "count": n} for name, n in by_template_rows],
            "avgTurnaroundDays": avg_turnaround_days,
            "avgTurnaroundTrend": avg_turnaround_trend,
            "backlog": [
                {
                    "id": str(b.id),
                    "code": b.code,
                    "templateName": b.template.name,
                    "status": b.status.value,
                    "currentStepOrder": b.current_step_order,
                    "daysWaiting": (now - b.submitted_at).days if b.submitted_at else 0,
                    "submittedAt": b.submitted_at,
                }
                for b in backlog_rows
            ],
            "rejectionRate30d": rejection_rate,
            "rejectionRateTrend": rejection_trend,
        }
