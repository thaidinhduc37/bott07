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
from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request
from zoneinfo import ZoneInfo

from app.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Schedule, StudyClass
from app.models.enums import NotificationType, RoleCode, ScheduleStatus
from app.models.notifications import Notification
from app.models.users import StudentProfile
from app.schemas.schedules import CreateScheduleDto, UpdateScheduleDto
from app.services.audit_service import AuditService
from app.services.schedule_csv import RowError, detect_conflicts, parse_exam_csv, parse_schedule_csv, sniff_is_exam

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
            .options(selectinload(Schedule.course))
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
                .options(selectinload(ExamSchedule.course))
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
            .options(selectinload(Schedule.course), selectinload(Schedule.study_class))
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

    async def _find_conflicts_in_db(
        self, *, class_id: str, room: str, instructor: str | None, starts_at: datetime, ends_at: datetime,
        exclude_id: str | None = None,
    ) -> list[Schedule]:
        overlap_conditions = [Schedule.class_id == class_id, Schedule.room == room]
        if instructor:
            overlap_conditions.append(Schedule.instructor == instructor)
        conditions = [
            Schedule.starts_at < ends_at, Schedule.ends_at > starts_at,
            or_(*overlap_conditions) if overlap_conditions else false(),
        ]
        stmt = select(Schedule).where(and_(*conditions))
        if exclude_id:
            stmt = stmt.where(Schedule.id != exclude_id)
        return list((await self.db.execute(stmt)).scalars().all())

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

        conflicts = await self._find_conflicts_in_db(
            class_id=dto.class_id, room=dto.room, instructor=dto.instructor, starts_at=starts_at, ends_at=ends_at,
        )
        if conflicts:
            raise HTTPException(
                status_code=400,
                detail={"message": "Lịch học bị trùng với buổi học khác (lớp/phòng/giảng viên)", "code": "SCHEDULE_CONFLICT"},
            )

        row = Schedule(
            class_id=dto.class_id, course_id=dto.course_id, academic_year=dto.academic_year, semester=dto.semester,
            session_date=session_date, week_number=dto.week_number,
            start_period=dto.start_period, end_period=dto.end_period, starts_at=starts_at, ends_at=ends_at,
            room=dto.room, building=dto.building, instructor=dto.instructor, delivery_mode=dto.delivery_mode,
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
        stmt = select(Schedule).options(selectinload(Schedule.course)).where(Schedule.id == id)
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

        conflicts = await self._find_conflicts_in_db(
            class_id=str(row.class_id), room=row.room, instructor=row.instructor,
            starts_at=row.starts_at, ends_at=row.ends_at, exclude_id=str(row.id),
        )
        if conflicts:
            raise HTTPException(
                status_code=400,
                detail={"message": "Lịch học bị trùng với buổi học khác (lớp/phòng/giảng viên)", "code": "SCHEDULE_CONFLICT"},
            )

        await self.db.flush()
        if changed_time_or_room_or_status:
            await self._notify_class(str(row.class_id), f'Lịch học đã được cập nhật: {row.course.name} ngày {row.session_date.strftime("%d/%m/%Y")}', row.id)
        await self.audit.log(
            action="SCHEDULE_UPDATE", user_id=user.id, entity_type="Schedule", entity_id=str(row.id), request=request,
        )
        await self.db.commit()
        return self._present_session(row)

    async def remove(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        stmt = select(Schedule).options(selectinload(Schedule.course)).where(Schedule.id == id)
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

        existing_external_ids = {r["external_id"] for r in valid_rows}
        model = ExamSchedule if is_exam else Schedule
        db_conflicts = await self._db_conflicts_for_import(model, valid_rows, existing_external_ids)
        for dc in db_conflicts:
            errors.append(dc)

        if errors and not allow_partial:
            return {
                "success": False, "dryRun": dry_run, "isExam": is_exam,
                "created": 0, "updated": 0, "errors": errors,
            }

        # Rows whose line number matches an error are skipped even under
        # allow_partial — only genuinely valid rows get written.
        error_lines = {e["line"] for e in errors}
        importable = [r for r in valid_rows if r["_line"] not in error_lines]

        if dry_run:
            return {
                "success": True, "dryRun": True, "isExam": is_exam,
                "created": None, "updated": None, "wouldImport": len(importable), "errors": errors,
            }

        created, updated = await self._upsert_rows(model, importable, class_id=str(study_class.id))

        if created or updated:
            noun = "lịch thi" if is_exam else "lịch học"
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

        return {"success": True, "dryRun": False, "isExam": is_exam, "created": created, "updated": updated, "errors": errors}

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
            .options(selectinload(ExamSchedule.course))
            .where(ExamSchedule.class_id == profile.class_id, ExamSchedule.starts_at >= start_utc, ExamSchedule.starts_at < end_utc)
            .order_by(ExamSchedule.starts_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return {"items": [self._present_exam(e) for e in rows]}

    # -------------------------------------------------------------- notify

    async def _notify_class(self, class_id: str, body: str, schedule_id) -> None:
        stmt = select(StudentProfile.user_id).where(StudentProfile.class_id == class_id)
        user_ids = [r[0] for r in (await self.db.execute(stmt)).all()]
        for uid in user_ids:
            self.db.add(Notification(
                user_id=uid, type=NotificationType.SCHEDULE_CHANGE, title="Thay đổi lịch học", body=body,
                link_to="/sinh-vien/lich",
            ))

    # ------------------------------------------------------------- present

    @staticmethod
    def _present_session(s: Schedule) -> dict:
        return {
            "id": str(s.id), "externalId": s.external_id, "academicYear": s.academic_year, "semester": s.semester,
            "classId": str(s.class_id), "courseId": str(s.course_id),
            "course": {
                "id": str(s.course.id), "code": s.course.code, "name": s.course.name, "credits": s.course.credits,
            } if s.course else None,
            "sessionDate": s.session_date, "weekNumber": s.week_number, "startPeriod": s.start_period,
            "endPeriod": s.end_period, "startsAt": s.starts_at, "endsAt": s.ends_at, "room": s.room,
            "building": s.building, "instructor": s.instructor, "deliveryMode": s.delivery_mode,
            "sessionType": s.session_type, "status": s.status, "note": s.note,
        }

    @staticmethod
    def _present_exam(e: ExamSchedule) -> dict:
        return {
            "id": str(e.id), "externalId": e.external_id, "academicYear": e.academic_year, "semester": e.semester,
            "classId": str(e.class_id), "courseId": str(e.course_id),
            "course": {
                "id": str(e.course.id), "code": e.course.code, "name": e.course.name, "credits": e.course.credits,
            } if e.course else None,
            "examDate": e.exam_date, "shift": e.shift, "startsAt": e.starts_at, "durationMinutes": e.duration_minutes,
            "endsAt": e.ends_at, "room": e.room, "building": e.building, "examFormat": e.exam_format,
            "examFormatRaw": e.exam_format_raw, "allowedMaterials": e.allowed_materials,
            "candidateCount": e.candidate_count, "chiefProctor": e.chief_proctor, "secondProctor": e.second_proctor,
            "status": e.status, "note": e.note,
        }
