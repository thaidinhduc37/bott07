"""Lịch thi và tra cứu phòng / giảng viên trống."""


from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Schedule, StudyClass
from app.models.enums import ExamFormat, ExamStatus, RoleCode, UserStatus
from app.models.users import Role, StudentProfile, User, UserRole
from app.services.academic.rooms_service import RoomsService, match_room, same_room
from app.schemas.schedules import (
    CreateExamDto,
    UpdateExamDto,
)
from app.services.academic.schedule_conflicts import (
    _is_unset_room,
)

from app.services.academic.schedule_common import (
    VN_TZ,
    _parse_range,
    _day_bounds_utc,
    _combine_vn_to_utc,
    _exam_opts,
)

class ExamsMixin:
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
