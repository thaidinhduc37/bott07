"""Class-session/exam schedules + CSV import. Port of the (deleted) NestJS
`schedules.service.ts`. Key properties preserved from the porting notes:

- A student's own timetable is always resolved from THEIR OWN
  `StudentProfile.class_id` — never accepted as a request parameter. This is
  a structural anti-IDOR: there is no `classId` argument on the student-self
  endpoints at all, so there is nothing a client could tamper with to see
  another class's schedule.
- All timestamps are stored in UTC but authored/displayed in VN local time
  (`Asia/Ho_Chi_Minh`) — conversion happens at the read/write boundary, not
  scattered through query logic.
- CSV import: row-level errors accumulate (not fail-fast), conflicts are
  checked both within the file and against the DB (excluding rows about to
  be overwritten by their own external_id — a re-import of the same row is
  an update, not a conflict with itself), and by default a file with ANY
  error is rejected wholesale (`allow_partial=True` opts into importing the
  good rows anyway). `dry_run=True` runs full validation without writing.
  Upsert key is `(academic_year, semester, external_id)` — re-importing the
  same `schedule_id`/`exam_id` updates the existing row rather than
  duplicating it. Missing courses referenced in the CSV are auto-created.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.base import NO_VALUE
from starlette.requests import Request
from zoneinfo import ZoneInfo

from app.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Schedule, StudyClass
from app.models.enums import ExamFormat, ExamStatus, NotificationType, RoleCode, ScheduleStatus, SessionType, UserStatus
from app.models.notifications import Notification
from app.models.users import Role, StudentProfile, User, UserRole
from app.services.rooms_service import RoomsService, match_room, same_room
from app.schemas.schedules import (
    CreateExamDto,
    CreateScheduleDto,
    UpdateExamDto,
    UpdateScheduleDto,
)
from app.services.audit_service import AuditService
from app.services.schedule_conflicts import (
    _is_unset_room,
    conflict_message,
    find_conflicts,
)
from app.services.schedule_csv import detect_conflicts, parse_exam_csv, parse_schedule_csv, sniff_is_exam

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


class SchedulesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # ---------------------------------------------------------- student self

    async def my_timetable(
        self, user_id: str, *, from_: str | None, to: str | None, include_exams: bool, course_id: str | None = None,
    ) -> dict:
        profile = (
            await self.db.execute(
                select(StudentProfile)
                .options(selectinload(StudentProfile.study_class))
                .where(StudentProfile.user_id == user_id)
            )
        ).scalar_one_or_none()

        d_from, d_to = _parse_range(from_, to)
        if not profile or not profile.class_id:
            return {
                "class": None,
                "range": {"from": d_from.isoformat(), "to": d_to.isoformat(), "timezone": "Asia/Ho_Chi_Minh"},
                "sessions": [], "exams": [],
            }

        start_utc, end_utc = _day_bounds_utc(d_from, d_to)
        sessions_stmt = (
            select(Schedule)
            .options(*_session_opts())
            .where(Schedule.class_id == profile.class_id, Schedule.starts_at >= start_utc, Schedule.starts_at < end_utc)
            .order_by(Schedule.starts_at.asc())
        )
        if course_id:
            sessions_stmt = sessions_stmt.where(Schedule.course_id == course_id)
        sessions = (await self.db.execute(sessions_stmt)).scalars().all()

        exams: list[ExamSchedule] = []
        if include_exams:
            exams_stmt = (
                select(ExamSchedule)
                .options(*_exam_opts())
                .where(ExamSchedule.class_id == profile.class_id, ExamSchedule.starts_at >= start_utc, ExamSchedule.starts_at < end_utc)
                .order_by(ExamSchedule.starts_at.asc())
            )
            if course_id:
                exams_stmt = exams_stmt.where(ExamSchedule.course_id == course_id)
            exams = (await self.db.execute(exams_stmt)).scalars().all()

        return {
            "class": {"id": str(profile.study_class.id), "code": profile.study_class.code, "name": profile.study_class.name}
            if profile.study_class else None,
            "range": {"from": d_from.isoformat(), "to": d_to.isoformat(), "timezone": "Asia/Ho_Chi_Minh"},
            "sessions": [self._present_session(s) for s in sessions],
            "exams": [self._present_exam(e) for e in exams],
        }

    async def my_courses(self, user_id: str) -> dict:
        profile = (await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))).scalar_one_or_none()
        if not profile or not profile.class_id:
            return {"items": []}
        stmt = (
            select(Course)
            .join(Schedule, Schedule.course_id == Course.id)
            .where(Schedule.class_id == profile.class_id)
            .distinct()
            .order_by(Course.code.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return {"items": [{"id": str(c.id), "code": c.code, "name": c.name, "credits": c.credits} for c in rows]}

    # -------------------------------------------------------------- staff view

    async def list(
        self, user: AuthenticatedUser, *, class_id: str | None, class_code: str | None, from_: str | None,
        to: str | None, course_id: str | None, page: int, page_size: int,
    ) -> dict:
        d_from, d_to = _parse_range(from_, to)
        start_utc, end_utc = _day_bounds_utc(d_from, d_to)

        stmt = (
            select(Schedule)
            .options(*_session_opts(), selectinload(Schedule.study_class))
            .where(Schedule.starts_at >= start_utc, Schedule.starts_at < end_utc)
        )
        if class_id:
            stmt = stmt.where(Schedule.class_id == class_id)
        if class_code:
            stmt = stmt.join(StudyClass, StudyClass.id == Schedule.class_id).where(StudyClass.code == class_code)
        if course_id:
            stmt = stmt.where(Schedule.course_id == course_id)

        is_staff_all = RoleCode.ADMIN.value in user.roles or RoleCode.ACADEMIC_MANAGER.value in user.roles
        if not is_staff_all and RoleCode.LECTURER.value in user.roles:
            stmt = stmt.join(Course, Course.id == Schedule.course_id).where(Course.lecturer_id == user.id)

        stmt = stmt.order_by(Schedule.starts_at.asc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().unique().all()
        return {"page": page, "pageSize": page_size, "items": [self._present_session(s) for s in rows]}

    # -------------------------------------------------------------- CRUD

    def _assert_can_edit(self, user: AuthenticatedUser, course: Course) -> None:
        if RoleCode.ADMIN.value in user.roles or RoleCode.ACADEMIC_MANAGER.value in user.roles:
            return
        if RoleCode.LECTURER.value in user.roles and course.lecturer_id and str(course.lecturer_id) == str(user.id):
            return
        raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền chỉnh sửa lịch của môn học này"})

    async def _class_headcount(self, class_id: str) -> int:
        return (
            await self.db.execute(
                select(func.count()).select_from(StudentProfile).where(StudentProfile.class_id == class_id)
            )
        ).scalar_one()

    async def _capacity_or_raise(self, *, class_id: str, room: str | None, building: str | None,
                                 headcount: int | None = None) -> None:
        """Phòng có trong danh mục và có sức chứa thì sĩ số lớp (hoặc số thí sinh) không được vượt quá."""
        if headcount is None:
            headcount = await self._class_headcount(class_id)
        await RoomsService(self.db).check_capacity(room=room, building=building, headcount=headcount)

    async def _conflict_or_raise(
        self, *, kind: str, class_id: str, room: str | None, building: str | None, course_id: str | None,
        instructor: str | None, starts_at: datetime, ends_at: datetime, exclude_id: str | None = None,
    ) -> None:
        """Kiểm tra trùng (lớp/phòng/giảng viên) với mọi buổi học + ca thi khác;
        nếu trùng thì ném lỗi 409 kèm danh sách buổi bị trùng."""
        conflicts = await find_conflicts(
            self.db,
            subj_kind=kind, class_id=class_id, room=room, building=building, course_id=course_id,
            instructor=instructor, starts_at=starts_at, ends_at=ends_at, exclude_id=exclude_id,
        )
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": conflict_message(conflicts),
                    "code": "SCHEDULE_CONFLICT",
                    "conflicts": conflicts,
                },
            )

    async def create(self, dto: CreateScheduleDto, user: AuthenticatedUser, request: Request | None) -> dict:
        study_class = await self.db.get(StudyClass, dto.class_id)
        if not study_class:
            raise HTTPException(status_code=400, detail={"message": "Không tìm thấy lớp học"})
        course = await self.db.get(Course, dto.course_id)
        if not course:
            raise HTTPException(status_code=400, detail={"message": "Không tìm thấy môn học"})
        self._assert_can_edit(user, course)

        if dto.end_period < dto.start_period:
            raise HTTPException(status_code=400, detail={"message": "Tiết kết thúc phải sau tiết bắt đầu"})

        try:
            session_date = date.fromisoformat(dto.session_date)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Ngày học không hợp lệ"})

        starts_at = _combine_vn_to_utc(session_date, dto.start_time)
        ends_at = _combine_vn_to_utc(session_date, dto.end_time)
        if ends_at <= starts_at:
            raise HTTPException(status_code=400, detail={"message": "Giờ kết thúc phải sau giờ bắt đầu"})

        # Tên người dạy: nếu bỏ trống mà môn có giảng viên phụ trách thì tự điền.
        instructor = dto.instructor
        if not (instructor or "").strip():
            # Nạp tường minh: `course.lecturer` chưa được selectinload, truy cập sẽ lazy-load (MissingGreenlet).
            lecturer = await self.db.get(User, course.lecturer_id) if course.lecturer_id else None
            if lecturer is not None:
                instructor = lecturer.full_name

        await self._conflict_or_raise(
            kind="SESSION", class_id=str(dto.class_id), room=dto.room, building=dto.building,
            course_id=str(dto.course_id), instructor=instructor, starts_at=starts_at, ends_at=ends_at,
        )
        await self._capacity_or_raise(class_id=str(dto.class_id), room=dto.room, building=dto.building)

        row = Schedule(
            class_id=dto.class_id, course_id=dto.course_id, academic_year=dto.academic_year, semester=dto.semester,
            session_date=session_date, week_number=dto.week_number,
            start_period=dto.start_period, end_period=dto.end_period, starts_at=starts_at, ends_at=ends_at,
            room=dto.room, building=dto.building, instructor=instructor, delivery_mode=dto.delivery_mode,
            session_type=dto.session_type, status=dto.status, note=dto.note,
        )
        # Set the relationship directly rather than relying on a lazy-load
        # later: `course` is already loaded in this session, and `_present_
        # session()` (a plain sync method) accessing `row.course` after this
        # point must never trigger an async lazy-load — that raises
        # MissingGreenlet outside the ORM's async bridge.
        row.course = course
        self.db.add(row)
        await self.db.flush()

        await self._notify_class(dto.class_id, f'Lịch học mới: {course.name} ngày {session_date.strftime("%d/%m/%Y")}', row.id)
        await self.audit.log(
            action="SCHEDULE_CREATE", user_id=user.id, entity_type="Schedule", entity_id=str(row.id), request=request,
        )
        await self.db.commit()
        return self._present_session(row)

    async def update(self, id: str, dto: UpdateScheduleDto, user: AuthenticatedUser, request: Request | None) -> dict:
        # Nạp sẵn course + lecturer + class để tự điền tên người dạy và kiểm tra
        # trùng mà không lazy-load (tránh MissingGreenlet).
        stmt = (
            select(Schedule)
            .options(
                *(_session_opts()),
                selectinload(Schedule.course).selectinload(Course.lecturer),
                selectinload(Schedule.study_class),
            )
            .where(Schedule.id == id)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lịch học"})
        self._assert_can_edit(user, row.course)

        changed_time_or_room_or_status = False
        if dto.course_id and dto.course_id != str(row.course_id):
            new_course = await self.db.get(Course, dto.course_id)
            if not new_course:
                raise HTTPException(status_code=400, detail={"message": "Không tìm thấy môn học"})
            row.course = new_course  # set the relationship, not just the FK, to avoid a later lazy-load

        session_date = row.session_date
        if dto.session_date:
            try:
                session_date = date.fromisoformat(dto.session_date)
            except ValueError:
                raise HTTPException(status_code=400, detail={"message": "Ngày học không hợp lệ"})
            row.session_date = session_date
            changed_time_or_room_or_status = True

        start_time = dto.start_time
        end_time = dto.end_time
        if start_time or end_time:
            existing_start_hm = row.starts_at.astimezone(VN_TZ).strftime("%H:%M")
            existing_end_hm = row.ends_at.astimezone(VN_TZ).strftime("%H:%M")
            new_starts_at = _combine_vn_to_utc(session_date, start_time or existing_start_hm)
            new_ends_at = _combine_vn_to_utc(session_date, end_time or existing_end_hm)
            if new_ends_at <= new_starts_at:
                raise HTTPException(status_code=400, detail={"message": "Giờ kết thúc phải sau giờ bắt đầu"})
            row.starts_at = new_starts_at
            row.ends_at = new_ends_at
            changed_time_or_room_or_status = True
        elif dto.session_date:
            # Date changed but times didn't -> re-derive starts_at/ends_at on the new date.
            existing_start_hm = row.starts_at.astimezone(VN_TZ).strftime("%H:%M")
            existing_end_hm = row.ends_at.astimezone(VN_TZ).strftime("%H:%M")
            row.starts_at = _combine_vn_to_utc(session_date, existing_start_hm)
            row.ends_at = _combine_vn_to_utc(session_date, existing_end_hm)

        if dto.week_number is not None:
            row.week_number = dto.week_number
        if dto.start_period is not None:
            row.start_period = dto.start_period
        if dto.end_period is not None:
            row.end_period = dto.end_period
        if row.end_period < row.start_period:
            raise HTTPException(status_code=400, detail={"message": "Tiết kết thúc phải sau tiết bắt đầu"})
        if dto.room is not None and dto.room != row.room:
            row.room = dto.room
            changed_time_or_room_or_status = True
        if dto.building is not None:
            row.building = dto.building
        if dto.instructor is not None:
            row.instructor = dto.instructor
        # Tên người dạy: nếu đang trống (và chưa được đặt ở trên) mà môn có giảng
        # viên phụ trách thì tự điền.
        if not (row.instructor or "").strip():
            lecturer = row.course.lecturer if row.course is not None else None
            if lecturer is not None:
                row.instructor = lecturer.full_name
        if dto.delivery_mode is not None:
            row.delivery_mode = dto.delivery_mode
        if dto.session_type is not None:
            row.session_type = dto.session_type
        if dto.status is not None:
            if dto.status != row.status and dto.status == ScheduleStatus.CANCELLED:
                changed_time_or_room_or_status = True
            row.status = dto.status
        if dto.note is not None:
            row.note = dto.note

        await self._conflict_or_raise(
            kind="SESSION", class_id=str(row.class_id), room=row.room, building=row.building,
            course_id=str(row.course_id), instructor=row.instructor,
            starts_at=row.starts_at, ends_at=row.ends_at, exclude_id=str(row.id),
        )
        if dto.room is not None or dto.building is not None:
            await self._capacity_or_raise(class_id=str(row.class_id), room=row.room, building=row.building)

        await self.db.flush()
        if changed_time_or_room_or_status:
            await self._notify_class(str(row.class_id), f'Lịch học đã được cập nhật: {row.course.name} ngày {row.session_date.strftime("%d/%m/%Y")}', row.id)
        await self.audit.log(
            action="SCHEDULE_UPDATE", user_id=user.id, entity_type="Schedule", entity_id=str(row.id), request=request,
        )
        await self.db.commit()
        return self._present_session(row)

    async def remove(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        stmt = select(Schedule).options(*_session_opts()).where(Schedule.id == id)
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lịch học"})
        self._assert_can_edit(user, row.course)

        class_id, course_name, session_date = str(row.class_id), row.course.name, row.session_date
        await self.db.delete(row)
        await self._notify_class(class_id, f'Lịch học đã bị hủy: {course_name} ngày {session_date.strftime("%d/%m/%Y")}', None)
        await self.audit.log(action="SCHEDULE_DELETE", user_id=user.id, entity_type="Schedule", entity_id=str(id), request=request)
        await self.db.commit()
        return {"message": "Đã xóa lịch học"}

    # ------------------------------------------------------------ CSV import

    async def import_schedules(
        self, *, file_bytes: bytes, filename: str | None, class_id: str, dry_run: bool, allow_partial: bool,
        user: AuthenticatedUser, request: Request | None,
    ) -> dict:
        study_class = await self.db.get(StudyClass, class_id)
        if not study_class:
            raise HTTPException(status_code=400, detail={"message": "Không tìm thấy lớp học"})

        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail={"message": "File CSV phải là UTF-8"})

        is_exam = sniff_is_exam(filename, text)
        parsed = parse_exam_csv(text) if is_exam else parse_schedule_csv(text)

        errors: list[dict] = [
            {"line": e.line, "column": e.column, "message": e.message} for e in parsed.errors
        ]
        total_rows = len(parsed.rows) + len({e.line for e in parsed.errors} - {r["_line"] for r in parsed.rows})
        conflicts: list[dict] = []

        def result(*, accepted: bool, imported: int, created: int | None, updated: int | None,
                   importable: int, new_courses: list[str], message: str) -> dict:
            """Khuôn kết quả đúng kiểu `ImportResult` phía client (trang Nạp lịch).
            Giữ thêm các khóa cũ (`success`, `isExam`, `wouldImport`) cho tương thích."""
            return {
                "fileName": filename or "",
                "class": study_class.code,
                **({"kind": "exam"} if is_exam else {}),
                "totalRows": total_rows,
                "validRows": importable,
                "errors": errors,
                "conflicts": conflicts,
                "dryRun": dry_run,
                "accepted": accepted,
                "imported": imported,
                "created": created,
                "updated": updated,
                "newCourses": new_courses,
                "message": message,
                "success": accepted,
                "isExam": is_exam,
                **({"wouldImport": importable} if dry_run else {}),
            }

        # Row-level: class_code in the file must match the target class
        # (single-class-per-import assumption, matching the demo's 1-class
        # scope) — mismatches are additional row errors, not silently ignored.
        valid_rows = []
        for row in parsed.rows:
            if row["class_code"] != study_class.code:
                errors.append({
                    "line": row["_line"], "column": "class_code",
                    "message": f'class_code "{row["class_code"]}" không khớp lớp đang nhập ("{study_class.code}")',
                })
                continue
            valid_rows.append(row)

        within_file_conflicts = detect_conflicts(valid_rows)
        for c in within_file_conflicts:
            errors.append({"line": c["lineB"], "column": "schedule", "message": f'{c["reason"]} (dòng {c["lineA"]})'})
            conflicts.append({
                "a": f'dòng {c["lineA"]}', "b": f'dòng {c["lineB"]}',
                "kind": "ROOM" if c["reason"].startswith("Trùng phòng")
                else "CLASS" if c["reason"] == "Trùng lịch của lớp" else "INSTRUCTOR",
                "message": c["reason"],
            })

        existing_external_ids = {r["external_id"] for r in valid_rows}
        model = ExamSchedule if is_exam else Schedule
        db_conflicts = await self._db_conflicts_for_import(model, valid_rows, existing_external_ids)
        for dc in db_conflicts:
            errors.append(dc)

        noun = "lịch thi" if is_exam else "lịch học"
        known_codes = {c for (c,) in (await self.db.execute(select(Course.code))).all()}
        new_courses = sorted({r["course_code"] for r in valid_rows} - known_codes)

        if errors and not allow_partial:
            return result(
                accepted=False, imported=0, created=0, updated=0,
                importable=len({r["_line"] for r in valid_rows} - {e["line"] for e in errors}),
                new_courses=[],
                message=f"Tệp {noun} có {len(errors)} lỗi nên chưa nạp gì. Sửa các dòng lỗi rồi nạp lại, "
                        "hoặc bật tùy chọn nạp các dòng hợp lệ.",
            )

        # Rows whose line number matches an error are skipped even under
        # allow_partial — only genuinely valid rows get written.
        error_lines = {e["line"] for e in errors}
        importable = [r for r in valid_rows if r["_line"] not in error_lines]

        if dry_run:
            return result(
                accepted=True, imported=0, created=None, updated=None, importable=len(importable),
                new_courses=new_courses,
                message=f"Kiểm tra thử: {len(importable)}/{total_rows} dòng {noun} hợp lệ, chưa ghi gì vào hệ thống.",
            )

        created, updated = await self._upsert_rows(model, importable, class_id=str(study_class.id))

        if created or updated:
            await self._notify_class(
                str(study_class.id),
                f'Đã cập nhật {noun}: {created} buổi mới, {updated} buổi thay đổi.',
                None,
            )

        await self.audit.log(
            action="SCHEDULE_IMPORT", user_id=user.id, entity_type="StudyClass", entity_id=str(study_class.id),
            detail={"isExam": is_exam, "created": created, "updated": updated, "errorCount": len(errors)},
            request=request,
        )
        await self.db.commit()

        return result(
            accepted=True, imported=created + updated, created=created, updated=updated,
            importable=len(importable), new_courses=new_courses,
            message=f"Đã nạp {created + updated} dòng {noun} ({created} mới, {updated} cập nhật)"
                    + (f"; bỏ qua {len(errors)} dòng lỗi." if errors else "."),
        )

    async def _db_conflicts_for_import(self, model, rows: list[dict], own_external_ids: set[str]) -> list[dict]:
        """Against-DB conflict check, excluding DB rows that are about to be
        overwritten by one of THIS file's own external_ids (a re-import
        updating its own row is not a conflict with itself)."""
        conflicts: list[dict] = []
        if not rows:
            return conflicts
        # Only bother querying the DB window actually touched by this batch.
        min_start = min(r["starts_at"] for r in rows)
        max_end = max(r["ends_at"] for r in rows)
        stmt = select(model).where(model.starts_at < max_end, model.ends_at > min_start)
        db_rows = (await self.db.execute(stmt)).scalars().all()
        db_rows = [d for d in db_rows if d.external_id not in own_external_ids]
        if not db_rows:
            return conflicts

        for r in rows:
            for d in db_rows:
                if r["starts_at"] < d.ends_at and r["ends_at"] > d.starts_at and r["room"] == d.room:
                    conflicts.append({
                        "line": r["_line"], "column": "room",
                        "message": f'Trùng phòng "{r["room"]}" với lịch đã có trong hệ thống ({d.external_id})',
                    })
        return conflicts

    async def _upsert_rows(self, model, rows: list[dict], *, class_id: str) -> tuple[int, int]:
        created = 0
        updated = 0
        for row in rows:
            course = (await self.db.execute(select(Course).where(Course.code == row["course_code"]))).scalar_one_or_none()
            if not course:
                course = Course(code=row["course_code"], name=row["course_name"], credits=row["credits"] or 0)
                self.db.add(course)
                await self.db.flush()

            existing = (
                await self.db.execute(
                    select(model).where(
                        model.academic_year == row["academic_year"], model.semester == row["semester"],
                        model.external_id == row["external_id"],
                    )
                )
            ).scalar_one_or_none()

            common = dict(
                external_id=row["external_id"], academic_year=row["academic_year"], semester=row["semester"],
                class_id=class_id, course_id=course.id, starts_at=row["starts_at"], ends_at=row["ends_at"],
                room=row["room"], building=row["building"], status=row["status"], note=row["note"],
            )
            if model is Schedule:
                common.update(
                    session_date=row["session_date"], week_number=row["week_number"],
                    start_period=row["start_period"], end_period=row["end_period"],
                    instructor=row["instructor"], delivery_mode=row["delivery_mode"], session_type=row["session_type"],
                )
            else:
                common.update(
                    exam_date=row["exam_date"], shift=row["shift"], duration_minutes=row["duration_minutes"],
                    exam_format=row["exam_format"], exam_format_raw=row["exam_format_raw"],
                    allowed_materials=row["allowed_materials"], candidate_count=row["candidate_count"],
                    chief_proctor=row["chief_proctor"], second_proctor=row["second_proctor"],
                )

            if existing is None:
                self.db.add(model(**common))
                created += 1
            else:
                for k, v in common.items():
                    if k in ("external_id", "academic_year", "semester"):
                        continue
                    setattr(existing, k, v)
                updated += 1
        await self.db.flush()
        return created, updated

    # -------------------------------------------------------------- exams

    async def exams_in_range(self, user_id: str, *, from_: str | None, to: str | None) -> dict:
        profile = (await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))).scalar_one_or_none()
        if not profile or not profile.class_id:
            return {"items": []}
        d_from, d_to = _parse_range(from_, to)
        start_utc, end_utc = _day_bounds_utc(d_from, d_to)
        stmt = (
            select(ExamSchedule)
            .options(*_exam_opts())
            .where(ExamSchedule.class_id == profile.class_id, ExamSchedule.starts_at >= start_utc, ExamSchedule.starts_at < end_utc)
            .order_by(ExamSchedule.starts_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return {"items": [self._present_exam(e) for e in rows]}

    # -------------------------------------------------------------- availability

    async def availability(
        self, *, day: str, start_time: str, end_time: str, exclude_id: str | None,
    ) -> dict:
        """Phòng / giảng viên nào đang bận trong khoảng giờ của một ngày (VN).

        Chỉ cán bộ quản lý + quản trị gọi được (kiểm tra ở router). ``rooms`` là
        tập (phòng, tòa nhà) từng xuất hiện trong lịch học + ca thi; ``lecturers``
        là giảng viên ACTIVE. ``by`` mô tả buổi khiến phòng/giảng viên bận."""
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Ngày không hợp lệ (YYYY-MM-DD)"})
        try:
            starts_at = _combine_vn_to_utc(d, start_time)
            ends_at = _combine_vn_to_utc(d, end_time)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Giờ không hợp lệ (HH:mm)"})
        if ends_at <= starts_at:
            raise HTTPException(status_code=400, detail={"message": "Giờ kết thúc phải sau giờ bắt đầu"})

        # Phòng = phòng đang sử dụng trong danh mục + phòng xuất hiện trong lịch mà chưa có trong danh mục.
        # Phòng đã NGỪNG sử dụng thì ẩn (kể cả khi lịch cũ còn nhắc tới nó).
        catalog = await RoomsService(self.db).all_rooms()
        room_entries: list[dict] = [
            {"room": r.code, "building": r.building, "capacity": r.capacity, "kind": r.kind, "registered": True}
            for r in catalog
            if r.is_active
        ]
        legacy: dict[tuple[str, str], tuple[str, str | None]] = {}
        for model in (Schedule, ExamSchedule):
            for r_code, r_building in (await self.db.execute(select(model.room, model.building))).all():
                if _is_unset_room(r_code) or match_room(catalog, r_code, r_building) is not None:
                    continue
                legacy.setdefault((r_code.strip().lower(), (r_building or "").strip().lower()), (r_code.strip(), r_building))
        room_entries.extend(
            {"room": code, "building": building, "capacity": None, "kind": None, "registered": False}
            for code, building in legacy.values()
        )
        room_entries.sort(key=lambda e: (e["room"].lower(), (e["building"] or "").lower()))

        # Nạp mọi buổi học + ca thi giao nhau với khoảng giờ, kèm course/class.
        s_stmt = (
            select(Schedule)
            .options(selectinload(Schedule.course), selectinload(Schedule.study_class))
            .where(Schedule.starts_at < ends_at, Schedule.ends_at > starts_at)
        )
        e_stmt = (
            select(ExamSchedule)
            .options(selectinload(ExamSchedule.course), selectinload(ExamSchedule.study_class))
            .where(ExamSchedule.starts_at < ends_at, ExamSchedule.ends_at > starts_at)
        )
        if exclude_id:
            s_stmt = s_stmt.where(Schedule.id != exclude_id)
            e_stmt = e_stmt.where(ExamSchedule.id != exclude_id)
        sessions = list((await self.db.execute(s_stmt)).scalars().unique().all())
        exams = list((await self.db.execute(e_stmt)).scalars().unique().all())

        def by_ref(row, course, cls) -> dict:
            return {
                "entryKind": "SESSION" if isinstance(row, Schedule) else "EXAM",
                "id": str(row.id),
                "course": {"code": course.code, "name": course.name} if course else None,
                "class": {"code": cls.code} if cls else None,
                "startsAt": row.starts_at,
                "endsAt": row.ends_at,
            }

        rooms_out: list[dict] = []
        for entry in room_entries:
            hit = None
            for s in sessions:
                if same_room(s.room, s.building, entry["room"], entry["building"]):
                    hit = by_ref(s, s.course, s.study_class)
                    break
            if hit is None:
                for e in exams:
                    if same_room(e.room, e.building, entry["room"], entry["building"]):
                        hit = by_ref(e, e.course, e.study_class)
                        break
            rooms_out.append({**entry, "busy": hit is not None, "by": hit})

        # Giảng viên ACTIVE có role LECTURER.
        role_row = (await self.db.execute(select(Role).where(Role.code == RoleCode.LECTURER))).scalar_one_or_none()
        lecturers: list[dict] = []
        if role_row is not None:
            lec_stmt = (
                select(User)
                .join(UserRole, UserRole.user_id == User.id)
                .where(UserRole.role_id == role_row.id, User.status == UserStatus.ACTIVE)
                .order_by(User.full_name.asc())
            )
            for u in (await self.db.execute(lec_stmt)).scalars().unique().all():
                hit = None
                for s in sessions:
                    if s.course is not None and s.course.lecturer_id and str(s.course.lecturer_id) == str(u.id):
                        hit = by_ref(s, s.course, s.study_class)
                        break
                if hit is None:
                    for e in exams:
                        if e.course is not None and e.course.lecturer_id and str(e.course.lecturer_id) == str(u.id):
                            hit = by_ref(e, e.course, e.study_class)
                            break
                lecturers.append({"id": str(u.id), "fullName": u.full_name, "busy": hit is not None, "by": hit})

        return {"date": day, "rooms": rooms_out, "lecturers": lecturers}

    # -------------------------------------------------------------- exam CRUD

    async def create_exam(self, dto: CreateExamDto, user: AuthenticatedUser, request: Request | None) -> dict:
        study_class = await self.db.get(StudyClass, dto.class_id)
        if not study_class:
            raise HTTPException(status_code=400, detail={"message": "Không tìm thấy lớp học"})
        course = await self.db.get(Course, dto.course_id)
        if not course:
            raise HTTPException(status_code=400, detail={"message": "Không tìm thấy môn học"})
        self._assert_can_edit(user, course)

        try:
            exam_date = date.fromisoformat(dto.exam_date)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Ngày thi không hợp lệ"})

        starts_at = _combine_vn_to_utc(exam_date, dto.start_time)
        ends_at = starts_at + timedelta(minutes=dto.duration_minutes)

        await self._conflict_or_raise(
            kind="EXAM", class_id=str(dto.class_id), room=dto.room, building=dto.building,
            course_id=str(dto.course_id), instructor=None, starts_at=starts_at, ends_at=ends_at,
        )
        # Ca thi: chỉ kiểm tra khi có khai báo số thí sinh (không suy ra từ sĩ số lớp).
        if dto.candidate_count is not None:
            await self._capacity_or_raise(
                class_id=str(dto.class_id), room=dto.room, building=dto.building, headcount=dto.candidate_count,
            )

        row = ExamSchedule(
            class_id=dto.class_id, course_id=dto.course_id, academic_year=dto.academic_year, semester=dto.semester,
            exam_date=exam_date, starts_at=starts_at, duration_minutes=dto.duration_minutes, ends_at=ends_at,
            room=dto.room, building=dto.building,
            exam_format=dto.exam_format or ExamFormat.TU_LUAN,
            allowed_materials=dto.allowed_materials, candidate_count=dto.candidate_count,
            chief_proctor=dto.chief_proctor, second_proctor=dto.second_proctor,
            status=ExamStatus.PUBLISHED, note=dto.note,
        )
        row.course = course
        self.db.add(row)
        await self.db.flush()

        await self._notify_class(
            str(dto.class_id),
            f'Lịch thi mới: {course.name} ngày {exam_date.strftime("%d/%m/%Y")}',
            row.id,
            title="Lịch thi mới",
        )
        await self.audit.log(
            action="EXAM_CREATE", user_id=user.id, entity_type="ExamSchedule", entity_id=str(row.id), request=request,
        )
        await self.db.commit()
        return self._present_exam(row)

    async def update_exam(self, id: str, dto: UpdateExamDto, user: AuthenticatedUser, request: Request | None) -> dict:
        stmt = (
            select(ExamSchedule)
            .options(
                *(_exam_opts()),
                selectinload(ExamSchedule.course).selectinload(Course.lecturer),
                selectinload(ExamSchedule.study_class),
            )
            .where(ExamSchedule.id == id)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy ca thi"})
        self._assert_can_edit(user, row.course)

        if dto.course_id and dto.course_id != str(row.course_id):
            new_course = await self.db.get(Course, dto.course_id)
            if not new_course:
                raise HTTPException(status_code=400, detail={"message": "Không tìm thấy môn học"})
            row.course = new_course

        if dto.academic_year is not None:
            row.academic_year = dto.academic_year
        if dto.semester is not None:
            row.semester = dto.semester

        exam_date = row.exam_date
        if dto.exam_date:
            try:
                exam_date = date.fromisoformat(dto.exam_date)
            except ValueError:
                raise HTTPException(status_code=400, detail={"message": "Ngày thi không hợp lệ"})
            row.exam_date = exam_date

        # Giờ bắt đầu / thời lượng: tính lại ends_at theo VN.
        new_duration = dto.duration_minutes if dto.duration_minutes is not None else row.duration_minutes
        if dto.start_time:
            row.starts_at = _combine_vn_to_utc(exam_date, dto.start_time)
        elif dto.exam_date:
            existing_hm = row.starts_at.astimezone(VN_TZ).strftime("%H:%M")
            row.starts_at = _combine_vn_to_utc(exam_date, existing_hm)
        row.duration_minutes = new_duration
        row.ends_at = row.starts_at + timedelta(minutes=new_duration)

        if dto.room is not None:
            row.room = dto.room
        if dto.building is not None:
            row.building = dto.building
        if dto.exam_format is not None:
            row.exam_format = dto.exam_format
        if dto.allowed_materials is not None:
            row.allowed_materials = dto.allowed_materials
        if dto.candidate_count is not None:
            row.candidate_count = dto.candidate_count
        if dto.chief_proctor is not None:
            row.chief_proctor = dto.chief_proctor
        if dto.second_proctor is not None:
            row.second_proctor = dto.second_proctor
        if dto.note is not None:
            row.note = dto.note

        await self._conflict_or_raise(
            kind="EXAM", class_id=str(row.class_id), room=row.room, building=row.building,
            course_id=str(row.course_id), instructor=None,
            starts_at=row.starts_at, ends_at=row.ends_at, exclude_id=str(row.id),
        )
        if row.candidate_count is not None and (dto.room is not None or dto.building is not None or dto.candidate_count is not None):
            await self._capacity_or_raise(
                class_id=str(row.class_id), room=row.room, building=row.building, headcount=row.candidate_count,
            )

        await self.db.flush()
        await self._notify_class(
            str(row.class_id),
            f'Lịch thi đã thay đổi: {row.course.name} ngày {row.exam_date.strftime("%d/%m/%Y")}',
            row.id,
            title="Lịch thi thay đổi",
        )
        await self.audit.log(
            action="EXAM_UPDATE", user_id=user.id, entity_type="ExamSchedule", entity_id=str(row.id), request=request,
        )
        await self.db.commit()
        return self._present_exam(row)

    async def delete_exam(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        stmt = select(ExamSchedule).options(*_exam_opts()).where(ExamSchedule.id == id)
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy ca thi"})
        self._assert_can_edit(user, row.course)

        class_id, course_name, exam_date = str(row.class_id), row.course.name, row.exam_date
        await self.db.delete(row)
        await self._notify_class(
            class_id,
            f'Lịch thi đã bị hủy: {course_name} ngày {exam_date.strftime("%d/%m/%Y")}',
            None,
            title="Lịch thi hủy",
        )
        await self.audit.log(
            action="EXAM_DELETE", user_id=user.id, entity_type="ExamSchedule", entity_id=str(id), request=request,
        )
        await self.db.commit()
        return {"message": "Đã xóa ca thi"}

    # -------------------------------------------------------------- lecturer

    async def teaching(
        self, user: AuthenticatedUser, *, from_: str | None, to: str | None, class_id: str | None,
    ) -> dict:
        """Buổi học + ca thi trong khoảng ngày mà người gọi được ghi chú.

        Giảng viên: chỉ các môn có `courses.lecturer_id` là mình. Cán bộ quản lý /
        quản trị: mọi môn (lọc thêm theo lớp nếu truyền `class_id`)."""
        d_from, d_to = _parse_range(from_, to)
        start_utc, end_utc = _day_bounds_utc(d_from, d_to)
        sees_all = RoleCode.ADMIN.value in user.roles or RoleCode.ACADEMIC_MANAGER.value in user.roles

        s_stmt = (
            select(Schedule)
            .options(*_session_opts(), selectinload(Schedule.study_class))
            .where(Schedule.starts_at >= start_utc, Schedule.starts_at < end_utc)
        )
        e_stmt = (
            select(ExamSchedule)
            .options(*_exam_opts(), selectinload(ExamSchedule.study_class))
            .where(ExamSchedule.starts_at >= start_utc, ExamSchedule.starts_at < end_utc)
        )
        if not sees_all:
            s_stmt = s_stmt.join(Course, Course.id == Schedule.course_id).where(Course.lecturer_id == user.id)
            e_stmt = e_stmt.join(Course, Course.id == ExamSchedule.course_id).where(Course.lecturer_id == user.id)
        if class_id:
            if not _is_uuid(class_id):
                raise HTTPException(status_code=400, detail={"message": "id lớp không hợp lệ"})
            s_stmt = s_stmt.where(Schedule.class_id == class_id)
            e_stmt = e_stmt.where(ExamSchedule.class_id == class_id)

        sessions = (await self.db.execute(s_stmt.order_by(Schedule.starts_at.asc()))).scalars().unique().all()
        exams = (await self.db.execute(e_stmt.order_by(ExamSchedule.starts_at.asc()))).scalars().unique().all()

        def with_class(row, presented: dict) -> dict:
            c = _loaded(row, "study_class")
            presented["class"] = {"id": str(c.id), "code": c.code, "name": c.name} if c else None
            return presented

        return {
            "range": {"from": d_from.isoformat(), "to": d_to.isoformat(), "timezone": "Asia/Ho_Chi_Minh"},
            "canEditAll": sees_all,
            "sessions": [with_class(x, self._present_session(x)) for x in sessions],
            "exams": [with_class(x, self._present_exam(x)) for x in exams],
        }

    async def set_lecturer_note(
        self, kind: str, id: str, note: str | None, *, notify: bool, user: AuthenticatedUser, request: Request | None,
    ) -> dict:
        """Ghi/xóa yêu cầu của giảng viên cho một buổi học hoặc ca thi.

        Quyền giống sửa lịch: giảng viên phụ trách môn, hoặc cán bộ quản lý / quản
        trị. Học viên của lớp nhận thông báo (trừ khi `notify=False` — sửa lỗi chính
        tả thì không cần làm phiền cả lớp)."""
        if not _is_uuid(id):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lịch"})
        model, opts, what = (
            (Schedule, _session_opts(), "buổi học") if kind == "SESSION" else (ExamSchedule, _exam_opts(), "ca thi")
        )
        row = (await self.db.execute(select(model).options(*opts).where(model.id == id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"message": f"Không tìm thấy {what}"})
        self._assert_can_edit(user, row.course)

        text = (note or "").strip() or None
        if text and len(text) > LECTURER_NOTE_MAX:
            raise HTTPException(status_code=400, detail={"message": f"Ghi chú tối đa {LECTURER_NOTE_MAX} ký tự"})
        if text == row.lecturer_note:
            return self._present_session(row) if kind == "SESSION" else self._present_exam(row)

        row.lecturer_note = text
        row.lecturer_note_updated_at = datetime.now(timezone.utc)
        row.lecturer_note_by_id = uuid.UUID(str(user.id))
        await self.db.flush()

        if notify and text:
            day = row.starts_at.astimezone(VN_TZ)
            link = f"/sinh-vien/lich?ngay={day.date().isoformat()}&buoi={kind}-{row.id}"
            label = "lịch thi" if kind == "EXAM" else "buổi học"
            await self._notify_class(
                str(row.class_id),
                f"{row.course.name} — {label} {day:%H:%M %d/%m}: {text[:160]}{'…' if len(text) > 160 else ''}",
                row.id,
                title=f"Giảng viên cập nhật yêu cầu cho {label}",
                link_to=link,
            )
        await self.audit.log(
            action="SCHEDULE_LECTURER_NOTE", user_id=user.id,
            entity_type="Schedule" if kind == "SESSION" else "ExamSchedule", entity_id=str(row.id),
            detail={"cleared": text is None, "notified": bool(notify and text)}, request=request,
        )
        await self.db.commit()

        fresh = (
            await self.db.execute(select(model).options(*opts).where(model.id == id).execution_options(populate_existing=True))
        ).scalar_one()
        return self._present_session(fresh) if kind == "SESSION" else self._present_exam(fresh)

    # -------------------------------------------------------------- notify

    async def _notify_class(
        self, class_id: str, body: str, schedule_id, *, title: str = "Thay đổi lịch học", link_to: str = "/sinh-vien/lich",
    ) -> None:
        stmt = select(StudentProfile.user_id).where(StudentProfile.class_id == class_id)
        user_ids = [r[0] for r in (await self.db.execute(stmt)).all()]
        for uid in user_ids:
            self.db.add(Notification(
                user_id=uid, type=NotificationType.SCHEDULE_CHANGE, title=title, body=body, link_to=link_to,
            ))

    # ------------------------------------------------------------- present

    @staticmethod
    def _course_ref(row) -> dict | None:
        c = _loaded(row, "course")
        return {"id": str(c.id), "code": c.code, "name": c.name, "credits": c.credits} if c else None

    @staticmethod
    def _present_session(s: Schedule) -> dict:
        session_type = _enum_value(s.session_type)
        status = _enum_value(s.status)
        return {
            "kind": "SESSION",
            "id": str(s.id), "externalId": s.external_id, "academicYear": s.academic_year, "semester": s.semester,
            "classId": str(s.class_id), "courseId": str(s.course_id),
            "course": SchedulesService._course_ref(s),
            "sessionDate": s.session_date, "weekNumber": s.week_number, "startPeriod": s.start_period,
            "endPeriod": s.end_period, "startsAt": s.starts_at, "endsAt": s.ends_at, "room": s.room,
            "building": s.building, "instructor": s.instructor, "deliveryMode": s.delivery_mode,
            "sessionType": session_type,
            "sessionTypeLabel": SESSION_TYPE_LABEL.get(SessionType(session_type), session_type) if session_type else None,
            "status": status,
            "statusLabel": SCHEDULE_STATUS_LABEL.get(ScheduleStatus(status), status) if status else None,
            "note": s.note,
            **_lecturer_block(s),
        }

    @staticmethod
    def _present_exam(e: ExamSchedule) -> dict:
        fmt = _enum_value(e.exam_format)
        return {
            "kind": "EXAM",
            "id": str(e.id), "externalId": e.external_id, "academicYear": e.academic_year, "semester": e.semester,
            "classId": str(e.class_id), "courseId": str(e.course_id),
            "course": SchedulesService._course_ref(e),
            "examDate": e.exam_date, "shift": e.shift, "startsAt": e.starts_at, "durationMinutes": e.duration_minutes,
            "endsAt": e.ends_at, "room": e.room, "building": e.building, "examFormat": fmt,
            "formatLabel": EXAM_FORMAT_LABEL.get(ExamFormat(fmt), e.exam_format_raw or fmt) if fmt else e.exam_format_raw,
            "examFormatRaw": e.exam_format_raw, "allowedMaterials": e.allowed_materials,
            "candidateCount": e.candidate_count, "chiefProctor": e.chief_proctor, "secondProctor": e.second_proctor,
            "status": _enum_value(e.status), "note": e.note,
            **_lecturer_block(e),
        }
