"""Catalog: CRUD Lớp / Môn học (gán giảng viên) + gán học viên vào lớp.

Quy tắc giữ nguyên từ các service khác:

- Mọi ghi đều kèm audit trong cùng transaction (`self.audit.log` rồi `commit`).
- Không lazy-load ngoài `await`: quan hệ cần dùng đều `selectinload` hoặc truy vấn tường minh.
- Lỗi chuẩn `HTTPException(detail={"message": ..., "code": ...})`.
- Id không tồn tại → 404 (không 500).
"""

from __future__ import annotations

import re
import uuid

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Faculty, Schedule, StudyClass
from app.models.documents import Document
from app.models.enums import NotificationType, RoleCode, UserStatus
from app.models.notifications import Notification
from app.models.users import StudentProfile, User, UserRole
from app.schemas.catalog import (
    AssignStudentsDto,
    CreateClassDto,
    CreateCourseDto,
    SetStudentClassDto,
    UpdateClassDto,
    UpdateCourseDto,
)
from app.services.audit_service import AuditService

_CODE_RE = re.compile(r"^[A-Z0-9_-]{1,30}$")


def _parse_uuid(value: str, label: str) -> str:
    """Id không hợp lệ UUID → 404 (yêu cầu của brief: không được 500)."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail={"message": f"Không tìm thấy {label}"})


class CatalogService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def _faculty_names(self) -> dict:
        """id → tên khoa, một truy vấn cho cả danh sách."""
        return {fid: name for fid, name in (await self.db.execute(select(Faculty.id, Faculty.name))).all()}

    async def _resolve_faculty(self, faculty_id: str | None) -> Faculty | None:
        """`facultyId` phải là khoa có thật; None = không xếp khoa."""
        if faculty_id is None:
            return None
        try:
            fid = uuid.UUID(faculty_id)
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(status_code=400, detail={"message": "Khoa không hợp lệ", "code": "INVALID_FACULTY"})
        row = await self.db.get(Faculty, fid)
        if not row:
            raise HTTPException(status_code=400, detail={"message": "Khoa không hợp lệ", "code": "INVALID_FACULTY"})
        return row

    # -------------------------------------------------------------- classes

    async def list_classes(self) -> dict:
        student_counts = {
            cid: n
            for cid, n in (
                await self.db.execute(
                    select(StudentProfile.class_id, func.count()).group_by(StudentProfile.class_id)
                )
            ).all()
            if cid is not None
        }
        session_counts = {
            cid: n
            for cid, n in (
                await self.db.execute(select(Schedule.class_id, func.count()).group_by(Schedule.class_id))
            ).all()
        }
        exam_counts = {
            cid: n
            for cid, n in (
                await self.db.execute(
                    select(ExamSchedule.class_id, func.count()).group_by(ExamSchedule.class_id)
                )
            ).all()
        }
        rows = (await self.db.execute(select(StudyClass).order_by(StudyClass.code.asc()))).scalars().all()
        faculties = await self._faculty_names()
        return {
            "items": [
                {
                    "id": str(c.id),
                    "code": c.code,
                    "name": c.name,
                    "faculty": faculties.get(c.faculty_id, c.faculty) if c.faculty_id else c.faculty,
                    "facultyId": str(c.faculty_id) if c.faculty_id else None,
                    "cohortYear": c.cohort_year,
                    "studentCount": student_counts.get(c.id, 0),
                    "sessionCount": session_counts.get(c.id, 0) + exam_counts.get(c.id, 0),
                }
                for c in rows
            ]
        }

    async def create_class(self, dto: CreateClassDto, user: AuthenticatedUser, request: Request | None) -> dict:
        code = dto.code.strip().upper()
        if not _CODE_RE.match(code):
            raise HTTPException(
                status_code=400,
                detail={"message": "Mã lớp chỉ gồm chữ hoa, số, dấu gạch ngang hoặc gạch dưới (1–30 ký tự)"},
            )
        existing = (await self.db.execute(select(StudyClass).where(StudyClass.code == code))).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409, detail={"message": f"Đã tồn tại lớp có mã {code}", "code": "CLASS_CODE_TAKEN"}
            )
        faculty_row = await self._resolve_faculty(dto.faculty_id)
        row = StudyClass(
            code=code,
            name=dto.name.strip(),
            # Có `facultyId` thì tên khoa dạng chữ lấy theo khoa đó; không thì giữ cách cũ (chuỗi tự do).
            faculty=faculty_row.name if faculty_row else (dto.faculty.strip() if dto.faculty else None),
            faculty_id=faculty_row.id if faculty_row else None,
            cohort_year=dto.cohort_year,
        )
        self.db.add(row)
        await self.db.flush()
        await self.audit.log(
            action="CLASS_CREATE", user_id=user.id, entity_type="StudyClass", entity_id=str(row.id),
            detail={"code": code, "name": row.name}, request=request,
        )
        await self.db.commit()
        return await self._present_class(str(row.id))

    async def update_class(
        self, id: str, dto: UpdateClassDto, user: AuthenticatedUser, request: Request | None
    ) -> dict:
        id = _parse_uuid(id, "lớp")
        row = await self.db.get(StudyClass, id)
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lớp"})

        payload = dto.model_dump(exclude_unset=True)
        changes: dict = {}

        if "code" in payload:
            new_code = (payload["code"] or "").strip().upper()
            if not _CODE_RE.match(new_code):
                raise HTTPException(
                    status_code=400,
                    detail={"message": "Mã lớp chỉ gồm chữ hoa, số, dấu gạch ngang hoặc gạch dưới (1–30 ký tự)"},
                )
            dup = (
                await self.db.execute(select(StudyClass).where(StudyClass.code == new_code, StudyClass.id != row.id))
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(
                    status_code=409, detail={"message": f"Đã tồn tại lớp có mã {new_code}", "code": "CLASS_CODE_TAKEN"}
                )
            if new_code != row.code:
                changes["code"] = {"from": row.code, "to": new_code}
                row.code = new_code
        if "name" in payload:
            new_name = (payload["name"] or "").strip() or row.name
            if new_name != row.name:
                changes["name"] = {"from": row.name, "to": new_name}
                row.name = new_name
        # `faculty`/`cohortYear` cho phép null để xóa — kiểm tra `in payload` chứ không phải truthy.
        if "faculty_id" in payload:
            faculty_row = await self._resolve_faculty(payload["faculty_id"])
            new_fid = faculty_row.id if faculty_row else None
            new_name = faculty_row.name if faculty_row else None
            if new_fid != row.faculty_id or new_name != row.faculty:
                changes["facultyId"] = {
                    "from": str(row.faculty_id) if row.faculty_id else None,
                    "to": str(new_fid) if new_fid else None,
                }
                row.faculty_id = new_fid
                row.faculty = new_name
        elif "faculty" in payload:
            new_faculty = payload["faculty"].strip() if payload["faculty"] else None
            if new_faculty != row.faculty:
                changes["faculty"] = {"from": row.faculty, "to": new_faculty}
                row.faculty = new_faculty
                # Sửa chuỗi tự do thì rời khỏi khoa có thực thể (hai nguồn không được lệch nhau).
                if row.faculty_id is not None:
                    row.faculty_id = None
        if "cohort_year" in payload and payload["cohort_year"] != row.cohort_year:
            changes["cohortYear"] = {"from": row.cohort_year, "to": payload["cohort_year"]}
            row.cohort_year = payload["cohort_year"]

        if not changes:
            return await self._present_class(id)

        await self.db.flush()
        await self.audit.log(
            action="CLASS_UPDATE", user_id=user.id, entity_type="StudyClass", entity_id=id,
            detail=changes, request=request,
        )
        await self.db.commit()
        return await self._present_class(id)

    async def delete_class(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        id = _parse_uuid(id, "lớp")
        row = await self.db.get(StudyClass, id)
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lớp"})

        n_students = (
            await self.db.execute(select(func.count()).select_from(StudentProfile).where(StudentProfile.class_id == row.id))
        ).scalar_one()
        n_sessions = (
            await self.db.execute(select(func.count()).select_from(Schedule).where(Schedule.class_id == row.id))
        ).scalar_one()
        n_exams = (
            await self.db.execute(
                select(func.count()).select_from(ExamSchedule).where(ExamSchedule.class_id == row.id)
            )
        ).scalar_one()
        if n_students or n_sessions or n_exams:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Lớp còn {n_students} học viên / {n_sessions + n_exams} buổi học nên chưa xóa được",
                    "code": "CLASS_IN_USE",
                },
            )

        await self.db.delete(row)
        await self.audit.log(
            action="CLASS_DELETE", user_id=user.id, entity_type="StudyClass", entity_id=id, request=request,
        )
        await self.db.commit()
        return {"message": "Đã xóa lớp"}

    async def _present_class(self, id: str) -> dict:
        row = await self.db.get(StudyClass, id)
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lớp"})
        n_students = (
            await self.db.execute(select(func.count()).select_from(StudentProfile).where(StudentProfile.class_id == row.id))
        ).scalar_one()
        n_sessions = (
            await self.db.execute(select(func.count()).select_from(Schedule).where(Schedule.class_id == row.id))
        ).scalar_one()
        n_exams = (
            await self.db.execute(
                select(func.count()).select_from(ExamSchedule).where(ExamSchedule.class_id == row.id)
            )
        ).scalar_one()
        return {
            "id": str(row.id),
            "code": row.code,
            "name": row.name,
            "faculty": row.faculty,
            "facultyId": str(row.faculty_id) if row.faculty_id else None,
            "cohortYear": row.cohort_year,
            "studentCount": n_students,
            "sessionCount": n_sessions + n_exams,
        }

    async def _present_course(self, id: str) -> dict:
        row = (
            await self.db.execute(select(Course).options(selectinload(Course.lecturer)).where(Course.id == id))
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})
        n_sessions = (
            await self.db.execute(select(func.count()).select_from(Schedule).where(Schedule.course_id == row.id))
        ).scalar_one()
        n_exams = (
            await self.db.execute(
                select(func.count()).select_from(ExamSchedule).where(ExamSchedule.course_id == row.id)
            )
        ).scalar_one()
        faculties = await self._faculty_names()
        return {
            "id": str(row.id),
            "code": row.code,
            "name": row.name,
            "credits": row.credits,
            "description": row.description,
            "facultyId": str(row.faculty_id) if row.faculty_id else None,
            "facultyName": faculties.get(row.faculty_id) if row.faculty_id else None,
            "lecturer": (
                {"id": str(row.lecturer.id), "fullName": row.lecturer.full_name, "email": row.lecturer.email}
                if row.lecturer
                else None
            ),
            "sessionCount": n_sessions + n_exams,
        }

    # -------------------------------------------------------------- courses

    async def list_courses(self) -> dict:
        session_counts = {
            cid: n
            for cid, n in (
                await self.db.execute(select(Schedule.course_id, func.count()).group_by(Schedule.course_id))
            ).all()
        }
        exam_counts = {
            cid: n
            for cid, n in (
                await self.db.execute(
                    select(ExamSchedule.course_id, func.count()).group_by(ExamSchedule.course_id)
                )
            ).all()
        }
        rows = (
            (
                await self.db.execute(
                    select(Course)
                    .options(selectinload(Course.lecturer))
                    .order_by(Course.code.asc())
                )
            )
            .scalars()
            .unique()
            .all()
        )
        faculties = await self._faculty_names()
        return {
            "items": [
                {
                    "id": str(c.id),
                    "code": c.code,
                    "name": c.name,
                    "credits": c.credits,
                    "description": c.description,
                    "facultyId": str(c.faculty_id) if c.faculty_id else None,
                    "facultyName": faculties.get(c.faculty_id) if c.faculty_id else None,
                    "lecturer": (
                        {"id": str(c.lecturer.id), "fullName": c.lecturer.full_name, "email": c.lecturer.email}
                        if c.lecturer
                        else None
                    ),
                    "sessionCount": session_counts.get(c.id, 0) + exam_counts.get(c.id, 0),
                }
                for c in rows
            ]
        }

    async def _validate_lecturer(self, lecturer_id: str | None) -> uuid.UUID | None:
        """`lecturerId` phải là user ACTIVE có role LECTURER (hoặc ACADEMIC_MANAGER)."""
        if lecturer_id is None:
            return None
        uid = _parse_uuid(lecturer_id, "giảng viên")
        user = await self.db.get(User, uid)
        if not user or user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=400, detail={"message": "Giảng viên không hợp lệ", "code": "INVALID_LECTURER"}
            )
        roles = {
            ur.role.code
            for ur in (
                await self.db.execute(
                    select(UserRole).options(selectinload(UserRole.role)).where(UserRole.user_id == uid)
                )
            ).scalars()
            if ur.role
        }
        if RoleCode.LECTURER not in roles and RoleCode.ACADEMIC_MANAGER not in roles:
            raise HTTPException(
                status_code=400, detail={"message": "Giảng viên không hợp lệ", "code": "INVALID_LECTURER"}
            )
        return uuid.UUID(uid)

    async def create_course(
        self, dto: CreateCourseDto, user: AuthenticatedUser, request: Request | None
    ) -> dict:
        code = dto.code.strip().upper()
        if not _CODE_RE.match(code):
            raise HTTPException(
                status_code=400,
                detail={"message": "Mã môn chỉ gồm chữ hoa, số, dấu gạch ngang hoặc gạch dưới (1–30 ký tự)"},
            )
        existing = (await self.db.execute(select(Course).where(Course.code == code))).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409, detail={"message": f"Đã tồn tại môn có mã {code}", "code": "COURSE_CODE_TAKEN"}
            )
        lecturer_id = await self._validate_lecturer(dto.lecturer_id)
        faculty_row = await self._resolve_faculty(dto.faculty_id)
        row = Course(
            code=code,
            name=dto.name.strip(),
            credits=dto.credits,
            description=dto.description.strip() if dto.description else None,
            lecturer_id=lecturer_id,
            faculty_id=faculty_row.id if faculty_row else None,
        )
        self.db.add(row)
        await self.db.flush()
        await self.audit.log(
            action="COURSE_CREATE", user_id=user.id, entity_type="Course", entity_id=str(row.id),
            detail={"code": code, "name": row.name, "lecturerId": str(lecturer_id) if lecturer_id else None},
            request=request,
        )
        await self.db.commit()
        return await self._present_course(str(row.id))

    async def update_course(
        self, id: str, dto: UpdateCourseDto, user: AuthenticatedUser, request: Request | None
    ) -> dict:
        id = _parse_uuid(id, "môn học")
        row = (
            await self.db.execute(select(Course).options(selectinload(Course.lecturer)).where(Course.id == id))
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})

        payload = dto.model_dump(exclude_unset=True)
        changes: dict = {}

        if "code" in payload:
            new_code = (payload["code"] or "").strip().upper()
            if not _CODE_RE.match(new_code):
                raise HTTPException(
                    status_code=400,
                    detail={"message": "Mã môn chỉ gồm chữ hoa, số, dấu gạch ngang hoặc gạch dưới (1–30 ký tự)"},
                )
            dup = (
                await self.db.execute(select(Course).where(Course.code == new_code, Course.id != row.id))
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(
                    status_code=409, detail={"message": f"Đã tồn tại môn có mã {new_code}", "code": "COURSE_CODE_TAKEN"}
                )
            if new_code != row.code:
                changes["code"] = {"from": row.code, "to": new_code}
                row.code = new_code
        if "name" in payload:
            new_name = (payload["name"] or "").strip() or row.name
            if new_name != row.name:
                changes["name"] = {"from": row.name, "to": new_name}
                row.name = new_name
        if "credits" in payload and payload["credits"] is not None and payload["credits"] != row.credits:
            changes["credits"] = {"from": row.credits, "to": payload["credits"]}
            row.credits = payload["credits"]
        # `description` cho phép null để xóa.
        if "description" in payload:
            new_desc = payload["description"].strip() if payload["description"] else None
            if new_desc != row.description:
                changes["description"] = {"from": row.description, "to": new_desc}
                row.description = new_desc

        if "faculty_id" in payload:
            faculty_row = await self._resolve_faculty(payload["faculty_id"])
            new_fid = faculty_row.id if faculty_row else None
            if new_fid != row.faculty_id:
                changes["facultyId"] = {
                    "from": str(row.faculty_id) if row.faculty_id else None,
                    "to": str(new_fid) if new_fid else None,
                }
                row.faculty_id = new_fid

        # Giảng viên: `lecturerId` có trong payload = có chủ ý (null = bỏ gán).
        new_lecturer_id: uuid.UUID | None = row.lecturer_id
        if "lecturer_id" in payload:
            new_lecturer_id = await self._validate_lecturer(payload["lecturer_id"])
            if new_lecturer_id != row.lecturer_id:
                changes["lecturerId"] = {
                    "from": str(row.lecturer_id) if row.lecturer_id else None,
                    "to": str(new_lecturer_id) if new_lecturer_id else None,
                }
                row.lecturer_id = new_lecturer_id
                row.lecturer = await self.db.get(User, new_lecturer_id) if new_lecturer_id else None

        if not changes:
            return await self._present_course(id)

        await self.db.flush()
        await self.audit.log(
            action="COURSE_UPDATE", user_id=user.id, entity_type="Course", entity_id=id,
            detail=changes, request=request,
        )
        # Đổi giảng viên → thông báo cho giảng viên mới.
        if "lecturerId" in changes and new_lecturer_id:
            self.db.add(
                Notification(
                    user_id=new_lecturer_id,
                    type=NotificationType.SYSTEM,
                    title="Phân công môn học mới",
                    body=f"Bạn được phân công phụ trách môn {row.name}",
                    link_to="/can-bo/lich",
                )
            )
        if "lecturerId" in changes:
            await self.audit.log(
                action="COURSE_LECTURER_ASSIGN", user_id=user.id, entity_type="Course", entity_id=id,
                detail={"lecturerId": changes["lecturerId"]}, request=request,
            )
        await self.db.commit()
        return await self._present_course(id)

    async def delete_course(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        id = _parse_uuid(id, "môn học")
        row = await self.db.get(Course, id)
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})

        n_sessions = (
            await self.db.execute(select(func.count()).select_from(Schedule).where(Schedule.course_id == row.id))
        ).scalar_one()
        n_exams = (
            await self.db.execute(
                select(func.count()).select_from(ExamSchedule).where(ExamSchedule.course_id == row.id)
            )
        ).scalar_one()
        n_docs = (
            await self.db.execute(select(func.count()).select_from(Document).where(Document.course_id == row.id))
        ).scalar_one()
        if n_sessions or n_exams or n_docs:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f"Môn còn {n_sessions + n_exams} buổi học/ca thi và {n_docs} tài liệu tham chiếu "
                        "nên chưa xóa được"
                    ),
                    "code": "COURSE_IN_USE",
                },
            )

        await self.db.delete(row)
        await self.audit.log(
            action="COURSE_DELETE", user_id=user.id, entity_type="Course", entity_id=id, request=request,
        )
        await self.db.commit()
        return {"message": "Đã xóa môn học"}

    # ------------------------------------------------------------- lecturers

    async def list_lecturers(self) -> dict:
        course_counts = {
            lid: n
            for lid, n in (
                await self.db.execute(
                    select(Course.lecturer_id, func.count()).where(Course.lecturer_id.is_not(None)).group_by(Course.lecturer_id)
                )
            ).all()
            if lid is not None
        }
        rows = (
            (
                await self.db.execute(
                    select(User)
                    .options(selectinload(User.roles).selectinload(UserRole.role))
                    .where(User.status == UserStatus.ACTIVE)
                    .order_by(User.full_name.asc())
                )
            )
            .scalars()
            .unique()
            .all()
        )
        faculties = await self._faculty_names()
        items = []
        for u in rows:
            codes = {ur.role.code for ur in u.roles if ur.role}
            if RoleCode.LECTURER not in codes:
                continue
            items.append(
                {
                    "id": str(u.id),
                    "fullName": u.full_name,
                    "email": u.email,
                    "courseCount": course_counts.get(u.id, 0),
                    "facultyId": str(u.faculty_id) if u.faculty_id else None,
                    "facultyName": faculties.get(u.faculty_id) if u.faculty_id else None,
                }
            )
        return {"items": items}

    # -------------------------------------------------------------- students

    async def list_students(
        self,
        *,
        class_id: str | None,
        search: str | None,
        unassigned: bool | None,
        page: int,
        page_size: int,
    ) -> dict:
        if class_id:
            class_id = _parse_uuid(class_id, "lớp")

        stmt = select(StudentProfile).options(
            selectinload(StudentProfile.user),
            selectinload(StudentProfile.study_class),
        )
        count_stmt = select(func.count()).select_from(StudentProfile)

        if class_id:
            stmt = stmt.where(StudentProfile.class_id == class_id)
            count_stmt = count_stmt.where(StudentProfile.class_id == class_id)
        if unassigned is True:
            stmt = stmt.where(StudentProfile.class_id.is_(None))
            count_stmt = count_stmt.where(StudentProfile.class_id.is_(None))
        elif unassigned is False:
            stmt = stmt.where(StudentProfile.class_id.is_not(None))
            count_stmt = count_stmt.where(StudentProfile.class_id.is_not(None))
        if search:
            term = f"%{search.strip()}%"
            cond = or_(
                StudentProfile.student_code.ilike(term),
                StudentProfile.cohort.ilike(term),
                StudentProfile.user.has(User.full_name.ilike(term)),
                StudentProfile.user.has(User.email.ilike(term)),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self.db.execute(count_stmt)).scalar_one()
        rows = (
            (
                await self.db.execute(
                    stmt.order_by(StudentProfile.student_code.asc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "items": [self._present_student(sp) for sp in rows],
        }

    @staticmethod
    def _present_student(sp: StudentProfile) -> dict:
        user = sp.user
        return {
            "id": str(sp.user_id),
            "studentCode": sp.student_code,
            "fullName": user.full_name if user else "",
            "email": user.email if user else "",
            "cohort": sp.cohort,
            "class": (
                {"id": str(sp.study_class.id), "code": sp.study_class.code, "name": sp.study_class.name}
                if sp.study_class
                else None
            ),
        }

    async def set_student_class(
        self, user_id: str, dto: SetStudentClassDto, user: AuthenticatedUser, request: Request | None
    ) -> dict:
        user_id = _parse_uuid(user_id, "học viên")
        sp = (await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))).scalar_one_or_none()
        if not sp:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy học viên"})

        new_class_id: uuid.UUID | None = None
        study_class: StudyClass | None = None
        if dto.class_id is not None:
            new_class_id = uuid.UUID(_parse_uuid(dto.class_id, "lớp"))
            study_class = await self.db.get(StudyClass, new_class_id)
            if not study_class:
                raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lớp"})

        if new_class_id == sp.class_id:
            return await self._present_student_fresh(user_id)

        sp.class_id = new_class_id
        await self.db.flush()

        if new_class_id and study_class:
            self.db.add(
                Notification(
                    user_id=user_id,
                    type=NotificationType.SYSTEM,
                    title="Xếp lớp mới",
                    body=f"Bạn được xếp vào lớp {study_class.name}",
                    link_to="/sinh-vien/lich",
                )
            )

        await self.audit.log(
            action="STUDENT_CLASS_ASSIGN",
            user_id=user.id,
            entity_type="StudentProfile",
            entity_id=str(sp.id),
            detail={
                "studentId": str(user_id),
                "classId": str(new_class_id) if new_class_id else None,
            },
            request=request,
        )
        await self.db.commit()
        return await self._present_student_fresh(user_id)

    async def assign_students(
        self, dto: AssignStudentsDto, user: AuthenticatedUser, request: Request | None
    ) -> dict:
        class_id = _parse_uuid(dto.class_id, "lớp")
        study_class = await self.db.get(StudyClass, class_id)
        if not study_class:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lớp"})

        # Chỉ lấy user có StudentProfile (bỏ qua user không phải học viên).
        stmt = select(StudentProfile).options(selectinload(StudentProfile.user)).where(
            StudentProfile.user_id.in_([uuid.UUID(_parse_uuid(uid, "học viên")) for uid in dto.user_ids])
        )
        profiles = (await self.db.execute(stmt)).scalars().unique().all()

        updated = 0
        for sp in profiles:
            if sp.class_id == study_class.id:
                continue
            sp.class_id = study_class.id
            updated += 1
            self.db.add(
                Notification(
                    user_id=sp.user_id,
                    type=NotificationType.SYSTEM,
                    title="Xếp lớp mới",
                    body=f"Bạn được xếp vào lớp {study_class.name}",
                    link_to="/sinh-vien/lich",
                )
            )

        await self.db.flush()
        await self.audit.log(
            action="STUDENT_CLASS_ASSIGN",
            user_id=user.id,
            entity_type="StudyClass",
            entity_id=str(study_class.id),
            detail={
                "requested": len(dto.user_ids),
                "updated": updated,
                "skipped": len(dto.user_ids) - len(profiles),
            },
            request=request,
        )
        await self.db.commit()
        return {"updated": updated, "skipped": len(dto.user_ids) - len(profiles)}

    async def _present_student_fresh(self, user_id: str) -> dict:
        sp = (
            (
                await self.db.execute(
                    select(StudentProfile)
                    .options(selectinload(StudentProfile.user), selectinload(StudentProfile.study_class))
                    .where(StudentProfile.user_id == user_id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .unique()
        ).one()
        return self._present_student(sp)
