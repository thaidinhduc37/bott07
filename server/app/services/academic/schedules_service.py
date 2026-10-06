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
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Schedule, StudyClass
from app.models.enums import ExamFormat, NotificationType, RoleCode, ScheduleStatus, SessionType
from app.models.notifications import Notification
from app.models.users import StudentProfile, User
from app.services.academic.rooms_service import RoomsService
from app.schemas.schedules import (
    CreateScheduleDto,
    UpdateScheduleDto,
)
from app.services.accounts.audit_service import AuditService
from app.services.academic.schedule_conflicts import (
    conflict_message,
    find_conflicts,
)

from app.services.academic.schedule_common import (
    VN_TZ,
    _is_uuid,
    _parse_range,
    _day_bounds_utc,
    _combine_vn_to_utc,
    SESSION_TYPE_LABEL,
    SCHEDULE_STATUS_LABEL,
    EXAM_FORMAT_LABEL,
    LECTURER_NOTE_MAX,
    _session_opts,
    _exam_opts,
    _loaded,
    _enum_value,
    _lecturer_block,
)
from app.services.academic.schedule_exams import ExamsMixin
from app.services.academic.schedule_import import ImportMixin

class SchedulesService(ImportMixin, ExamsMixin):
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
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"message": "Ngày học không hợp lệ"}) from exc

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
            except ValueError as exc:
                raise HTTPException(status_code=400, detail={"message": "Ngày học không hợp lệ"}) from exc
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
