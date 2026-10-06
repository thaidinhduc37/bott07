"""Tiện ích dùng chung của dịch vụ lịch học/lịch thi: múi giờ VN, đổi ngày giờ, nhãn, trình bày."""


from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.base import NO_VALUE
from zoneinfo import ZoneInfo

from app.models.academic import Course, ExamSchedule, Schedule
from app.models.enums import ExamFormat, ScheduleStatus, SessionType

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _current_week_range_vn() -> tuple[date, date]:
    now_vn = datetime.now(VN_TZ)
    monday = now_vn.date() - timedelta(days=now_vn.weekday())
    return monday, monday + timedelta(days=6)


def _parse_range(from_: str | None, to: str | None) -> tuple[date, date]:
    if from_ and to:
        try:
            return date.fromisoformat(from_), date.fromisoformat(to)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Khoảng ngày không hợp lệ (YYYY-MM-DD)"})
    return _current_week_range_vn()


def _day_bounds_utc(d_from: date, d_to: date) -> tuple[datetime, datetime]:
    start = datetime(d_from.year, d_from.month, d_from.day, tzinfo=VN_TZ).astimezone(timezone.utc)
    end_local_day = d_to + timedelta(days=1)
    end = datetime(end_local_day.year, end_local_day.month, end_local_day.day, tzinfo=VN_TZ).astimezone(timezone.utc)
    return start, end


def _combine_vn_to_utc(d: date, hh_mm: str) -> datetime:
    h, m = (int(x) for x in hh_mm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=VN_TZ).astimezone(timezone.utc)


@dataclass
class ImportOutcome:
    success: bool
    dry_run: bool
    created: int = 0
    updated: int = 0
    errors: list[dict] | None = None


SESSION_TYPE_LABEL = {
    SessionType.LY_THUYET: "Lý thuyết",
    SessionType.THUC_HANH: "Thực hành",
    SessionType.KIEM_TRA_GIUA_KY: "Kiểm tra giữa kỳ",
    SessionType.ON_TAP: "Ôn tập",
    SessionType.HOC_BU: "Học bù",
}
SCHEDULE_STATUS_LABEL = {
    ScheduleStatus.SCHEDULED: "Theo lịch",
    ScheduleStatus.CANCELLED: "Đã hủy",
    ScheduleStatus.HOLIDAY: "Nghỉ lễ",
    ScheduleStatus.COMPLETED: "Đã học",
}
EXAM_FORMAT_LABEL = {
    ExamFormat.TRAC_NGHIEM: "Trắc nghiệm",
    ExamFormat.TU_LUAN: "Tự luận",
    ExamFormat.THUC_HANH: "Thực hành",
    ExamFormat.KET_HOP: "Kết hợp",
}
LECTURER_NOTE_MAX = 4000


def _session_opts():
    """Nạp sẵn môn + giảng viên phụ trách + người sửa ghi chú: `_present_*` là hàm
    đồng bộ, không được kích hoạt lazy-load async."""
    return (
        selectinload(Schedule.course).selectinload(Course.lecturer),
        selectinload(Schedule.lecturer_note_by),
    )


def _exam_opts():
    return (
        selectinload(ExamSchedule.course).selectinload(Course.lecturer),
        selectinload(ExamSchedule.lecturer_note_by),
    )


def _loaded(obj, attr: str):
    """Giá trị quan hệ nếu ĐÃ nạp, ngược lại None — không bao giờ tự nạp."""
    if obj is None:
        return None
    value = sa_inspect(obj).attrs[attr].loaded_value
    return None if value is NO_VALUE else value


def _enum_value(v):
    return v.value if hasattr(v, "value") else v


def _lecturer_block(row) -> dict:
    course = _loaded(row, "course")
    lecturer = _loaded(course, "lecturer") if course is not None else None
    by = _loaded(row, "lecturer_note_by")
    return {
        # Giảng viên phụ trách MÔN (tài khoản trong hệ thống) — khác `instructor` là
        # tên người đứng lớp của riêng buổi đó lấy từ CSV (có thể là người dạy thay).
        "lecturer": {"id": str(lecturer.id), "name": lecturer.full_name, "email": lecturer.email} if lecturer else None,
        "lecturerNote": {
            "text": row.lecturer_note,
            "updatedAt": row.lecturer_note_updated_at,
            "updatedBy": by.full_name if by else None,
        } if row.lecturer_note else None,
    }
