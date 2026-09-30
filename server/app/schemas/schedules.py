"""Request DTOs for schedules/exams/CSV import. Response shapes are plain
dicts built by hand in the service layer (same convention as forms/chat/
documents in this codebase)."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from app.models.enums import ExamFormat, ExamStatus, ScheduleStatus, SessionType
from app.schemas.base import CamelModel

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleRangeDto(CamelModel):
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    course_id: str | None = None
    include_exams: bool = True


class AdminScheduleQueryDto(ScheduleRangeDto):
    class_id: str | None = None
    class_code: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


class CreateScheduleDto(CamelModel):
    class_id: str
    course_id: str
    academic_year: str = Field(..., max_length=20)
    semester: str = Field(..., max_length=20)
    session_date: str
    week_number: int | None = None
    start_period: int = Field(..., ge=1, le=20)
    end_period: int = Field(..., ge=1, le=20)
    start_time: str
    end_time: str
    room: str = Field(..., max_length=50)
    building: str | None = Field(default=None, max_length=100)
    instructor: str | None = Field(default=None, max_length=150)
    delivery_mode: str | None = Field(default=None, max_length=50)
    session_type: SessionType = SessionType.LY_THUYET
    status: ScheduleStatus = ScheduleStatus.SCHEDULED
    note: str | None = Field(default=None, max_length=500)

    @field_validator("start_time", "end_time")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("phải theo định dạng HH:mm")
        return v


class UpdateScheduleDto(CamelModel):
    course_id: str | None = None
    session_date: str | None = None
    week_number: int | None = None
    start_period: int | None = Field(default=None, ge=1, le=20)
    end_period: int | None = Field(default=None, ge=1, le=20)
    start_time: str | None = None
    end_time: str | None = None
    room: str | None = Field(default=None, max_length=50)
    building: str | None = Field(default=None, max_length=100)
    instructor: str | None = Field(default=None, max_length=150)
    delivery_mode: str | None = Field(default=None, max_length=50)
    session_type: SessionType | None = None
    status: ScheduleStatus | None = None
    note: str | None = Field(default=None, max_length=500)

    @field_validator("start_time", "end_time")
    @classmethod
    def _valid_time(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_RE.match(v):
            raise ValueError("phải theo định dạng HH:mm")
        return v


class ImportScheduleDto(CamelModel):
    class_id: str
    dry_run: bool = False
    allow_partial: bool = False


class CreateExamDto(CamelModel):
    class_id: str
    course_id: str
    academic_year: str = Field(..., max_length=20)
    semester: str = Field(..., max_length=20)
    exam_date: str
    start_time: str
    duration_minutes: int = Field(..., ge=15, le=480)
    room: str = Field(..., max_length=50)
    building: str | None = Field(default=None, max_length=100)
    exam_format: ExamFormat | None = None
    allowed_materials: str | None = Field(default=None, max_length=300)
    candidate_count: int | None = Field(default=None, ge=0)
    chief_proctor: str | None = Field(default=None, max_length=150)
    second_proctor: str | None = Field(default=None, max_length=150)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("start_time")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("phải theo định dạng HH:mm")
        return v


class UpdateExamDto(CamelModel):
    """Mọi trường tùy chọn; lớp không đổi (không có `class_id` ở đây)."""

    course_id: str | None = None
    academic_year: str | None = Field(default=None, max_length=20)
    semester: str | None = Field(default=None, max_length=20)
    exam_date: str | None = None
    start_time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    room: str | None = Field(default=None, max_length=50)
    building: str | None = Field(default=None, max_length=100)
    exam_format: ExamFormat | None = None
    allowed_materials: str | None = Field(default=None, max_length=300)
    candidate_count: int | None = Field(default=None, ge=0)
    chief_proctor: str | None = Field(default=None, max_length=150)
    second_proctor: str | None = Field(default=None, max_length=150)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("start_time")
    @classmethod
    def _valid_time(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_RE.match(v):
            raise ValueError("phải theo định dạng HH:mm")
        return v


class ExamRangeDto(CamelModel):
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None


class LecturerNoteDto(CamelModel):
    """Yêu cầu của giảng viên cho một buổi học / ca thi. Rỗng hoặc null = xóa."""

    note: str | None = Field(default=None, max_length=4000)
    # Gửi thông báo cho học viên của lớp. Tắt khi chỉ sửa lỗi chính tả.
    notify: bool = True
