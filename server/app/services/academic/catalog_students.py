"""Học viên: danh sách, đổi lớp, gán hàng loạt."""


from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import StudyClass
from app.models.enums import NotificationType
from app.models.notifications import Notification
from app.models.users import StudentProfile, User
from app.schemas.catalog import (
    AssignStudentsDto,
    SetStudentClassDto,
)

from app.services.academic.catalog_common import _parse_uuid

class StudentsMixin:
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
