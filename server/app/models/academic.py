from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import TIMESTAMPTZ, created_at_col, updated_at_col, uuid_pk
from app.models.enums import ExamFormat, ExamStatus, ScheduleStatus, SessionType


class Faculty(Base):
    """Khoa. Trưởng khoa (`head_id`) có quyền xem và phân công trong phạm vi khoa mình."""

    __tablename__ = "faculties"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    head_id: Mapped[uuid.UUID | None] = mapped_column(
        "head_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()

    head: Mapped["User | None"] = relationship(foreign_keys=[head_id])


class Room(Base):
    """Danh mục phòng học / phòng thi. `schedules.room` vẫn là chuỗi (tương thích CSV); danh mục này
    để chọn, gợi ý và kiểm tra sức chứa."""

    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String, nullable=False)
    building: Mapped[str | None] = mapped_column(String, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str | None] = mapped_column(String, nullable=True)  # vd "Lý thuyết", "Thực hành", "Hội trường"
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column("is_active", Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()


class StudyClass(Base):
    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Tên khoa dạng chữ (cũ) — giữ đồng bộ với `faculty_id` để không vỡ chỗ đang đọc.
    faculty: Mapped[str | None] = mapped_column(String, nullable=True)
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(
        "faculty_id", PGUUID(as_uuid=True), ForeignKey("faculties.id", ondelete="SET NULL"), nullable=True
    )
    cohort_year: Mapped[int | None] = mapped_column("cohort_year", Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    students: Mapped[list["StudentProfile"]] = relationship(back_populates="study_class")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="study_class")
    exam_schedules: Mapped[list["ExamSchedule"]] = relationship(back_populates="study_class")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(
        "faculty_id", PGUUID(as_uuid=True), ForeignKey("faculties.id", ondelete="SET NULL"), nullable=True
    )
    lecturer_id: Mapped[uuid.UUID | None] = mapped_column(
        "lecturer_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()

    lecturer: Mapped["User | None"] = relationship(back_populates="taught_courses")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="course")
    exam_schedules: Mapped[list["ExamSchedule"]] = relationship(back_populates="course")
    documents: Mapped[list["Document"]] = relationship(back_populates="course")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = uuid_pk()
    external_id: Mapped[str | None] = mapped_column("external_id", String, nullable=True)
    academic_year: Mapped[str] = mapped_column("academic_year", String, nullable=False)
    semester: Mapped[str] = mapped_column(String, nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(
        "class_id", PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        "course_id", PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    session_date: Mapped[date] = mapped_column("session_date", Date, nullable=False)
    week_number: Mapped[int | None] = mapped_column("week_number", Integer, nullable=True)
    start_period: Mapped[int] = mapped_column("start_period", Integer, nullable=False)
    end_period: Mapped[int] = mapped_column("end_period", Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column("starts_at", TIMESTAMPTZ, nullable=False)
    ends_at: Mapped[datetime] = mapped_column("ends_at", TIMESTAMPTZ, nullable=False)
    room: Mapped[str] = mapped_column(String, nullable=False)
    building: Mapped[str | None] = mapped_column(String, nullable=True)
    instructor: Mapped[str | None] = mapped_column(String, nullable=True)
    delivery_mode: Mapped[str | None] = mapped_column("delivery_mode", String, nullable=True)
    session_type: Mapped[SessionType] = mapped_column(
        "session_type", SAEnum(SessionType, name="SessionType", native_enum=True), default=SessionType.LY_THUYET
    )
    status: Mapped[ScheduleStatus] = mapped_column(
        SAEnum(ScheduleStatus, name="ScheduleStatus", native_enum=True), default=ScheduleStatus.SCHEDULED
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    # Yêu cầu/ghi chú của giảng viên cho riêng buổi này (chuẩn bị gì, mang gì, đọc
    # trước chương nào...). Tách khỏi `note`: `note` đến từ tệp CSV và bị ghi đè
    # mỗi lần nạp lại lịch; cột này chỉ giảng viên/cán bộ sửa qua giao diện.
    lecturer_note: Mapped[str | None] = mapped_column("lecturer_note", Text, nullable=True)
    lecturer_note_updated_at: Mapped[datetime | None] = mapped_column("lecturer_note_updated_at", TIMESTAMPTZ, nullable=True)
    lecturer_note_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "lecturer_note_by_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lecturer_note_by: Mapped["User | None"] = relationship(foreign_keys=[lecturer_note_by_id])
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    study_class: Mapped["StudyClass"] = relationship(back_populates="schedules")
    course: Mapped["Course"] = relationship(back_populates="schedules")

    __table_args__ = (
        UniqueConstraint("academic_year", "semester", "external_id", name="uq_schedules_year_sem_extid"),
        Index("ix_schedules_class_id_starts_at", "class_id", "starts_at"),
        Index("ix_schedules_course_id_starts_at", "course_id", "starts_at"),
    )


class ExamSchedule(Base):
    __tablename__ = "exam_schedules"

    id: Mapped[uuid.UUID] = uuid_pk()
    external_id: Mapped[str | None] = mapped_column("external_id", String, nullable=True)
    academic_year: Mapped[str] = mapped_column("academic_year", String, nullable=False)
    semester: Mapped[str] = mapped_column(String, nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(
        "class_id", PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        "course_id", PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    exam_date: Mapped[date] = mapped_column("exam_date", Date, nullable=False)
    shift: Mapped[str | None] = mapped_column(String, nullable=True)
    starts_at: Mapped[datetime] = mapped_column("starts_at", TIMESTAMPTZ, nullable=False)
    duration_minutes: Mapped[int] = mapped_column("duration_minutes", Integer, nullable=False)
    ends_at: Mapped[datetime] = mapped_column("ends_at", TIMESTAMPTZ, nullable=False)
    room: Mapped[str] = mapped_column(String, nullable=False)
    building: Mapped[str | None] = mapped_column(String, nullable=True)
    exam_format: Mapped[ExamFormat] = mapped_column(
        "exam_format", SAEnum(ExamFormat, name="ExamFormat", native_enum=True), default=ExamFormat.TU_LUAN
    )
    exam_format_raw: Mapped[str | None] = mapped_column("exam_format_raw", String, nullable=True)
    allowed_materials: Mapped[str | None] = mapped_column("allowed_materials", String, nullable=True)
    candidate_count: Mapped[int | None] = mapped_column("candidate_count", Integer, nullable=True)
    chief_proctor: Mapped[str | None] = mapped_column("chief_proctor", String, nullable=True)
    second_proctor: Mapped[str | None] = mapped_column("second_proctor", String, nullable=True)
    status: Mapped[ExamStatus] = mapped_column(
        SAEnum(ExamStatus, name="ExamStatus", native_enum=True), default=ExamStatus.PUBLISHED
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    # Yêu cầu/ghi chú của giảng viên cho riêng buổi này (chuẩn bị gì, mang gì, đọc
    # trước chương nào...). Tách khỏi `note`: `note` đến từ tệp CSV và bị ghi đè
    # mỗi lần nạp lại lịch; cột này chỉ giảng viên/cán bộ sửa qua giao diện.
    lecturer_note: Mapped[str | None] = mapped_column("lecturer_note", Text, nullable=True)
    lecturer_note_updated_at: Mapped[datetime | None] = mapped_column("lecturer_note_updated_at", TIMESTAMPTZ, nullable=True)
    lecturer_note_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "lecturer_note_by_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lecturer_note_by: Mapped["User | None"] = relationship(foreign_keys=[lecturer_note_by_id])
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    study_class: Mapped["StudyClass"] = relationship(back_populates="exam_schedules")
    course: Mapped["Course"] = relationship(back_populates="exam_schedules")

    __table_args__ = (
        UniqueConstraint("academic_year", "semester", "external_id", name="uq_exam_schedules_year_sem_extid"),
        Index("ix_exam_schedules_class_id_starts_at", "class_id", "starts_at"),
    )


# String-only forward references above (`"User"`, `"StudentProfile"`, `"Document"`,
# `"QuizSession"`) are resolved through the shared `Base.registry` once every
# model module has been imported — see `app/models/__init__.py`.
