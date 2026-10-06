"""Lớp học: danh sách, tạo, sửa, xóa."""


from __future__ import annotations


from fastapi import HTTPException
from sqlalchemy import func, select
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import ExamSchedule, Schedule, StudyClass
from app.models.users import StudentProfile
from app.schemas.catalog import (
    CreateClassDto,
    UpdateClassDto,
)

from app.services.academic.catalog_common import _CODE_RE, _parse_uuid

class ClassesMixin:
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
