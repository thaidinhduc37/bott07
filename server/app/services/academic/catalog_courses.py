"""Môn học và giảng viên phụ trách."""


from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Schedule
from app.models.documents import Document
from app.models.enums import NotificationType, RoleCode, UserStatus
from app.models.notifications import Notification
from app.models.users import User, UserRole
from app.schemas.catalog import (
    CreateCourseDto,
    UpdateCourseDto,
)

from app.services.academic.catalog_common import _CODE_RE, _parse_uuid

class CoursesMixin:
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
