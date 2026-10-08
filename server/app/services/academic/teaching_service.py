"""Lớp của giảng viên: các lớp có lịch môn do mình phụ trách, danh sách học viên (chỉ đọc) và buổi học sắp tới.

Giảng viên không sở hữu danh mục lớp: việc tạo/sửa lớp và xếp học viên vào lớp vẫn thuộc quản lý đào tạo.
Một lớp "của tôi" khi có ít nhất một buổi học (`schedules`) của môn có `courses.lecturer_id` là mình.
Chỉ trả mã và họ tên học viên — đúng phạm vi danh sách nhập điểm.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser
from app.models.academic import Course, Schedule, StudyClass
from app.models.users import StudentProfile, User
from app.services.academic.csv_export import csv_response


def _course_ref(c: Course) -> dict:
    return {"id": str(c.id), "code": c.code, "name": c.name, "credits": c.credits}


class TeachingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _taught(self, user: AuthenticatedUser, class_id: uuid.UUID | None = None) -> dict[uuid.UUID, dict[uuid.UUID, Course]]:
        """{lớp: {môn: Course}} của các cặp (lớp, môn) giảng viên có lịch."""
        stmt = (
            select(Schedule.class_id, Course)
            .join(Course, Course.id == Schedule.course_id)
            .where(Course.lecturer_id == uuid.UUID(user.id))
            .distinct()
        )
        if class_id is not None:
            stmt = stmt.where(Schedule.class_id == class_id)
        out: dict[uuid.UUID, dict[uuid.UUID, Course]] = {}
        for clid, course in (await self.db.execute(stmt)).all():
            out.setdefault(clid, {})[course.id] = course
        return out

    async def list_classes(self, user: AuthenticatedUser) -> dict:
        taught = await self._taught(user)
        if not taught:
            return {"items": []}
        classes = (await self.db.execute(select(StudyClass).where(StudyClass.id.in_(taught)))).scalars().all()
        sizes = dict(
            (await self.db.execute(
                select(StudentProfile.class_id, func.count()).where(StudentProfile.class_id.in_(taught)).group_by(StudentProfile.class_id)
            )).all()
        )
        my_courses = {course_id for courses in taught.values() for course_id in courses}
        next_session = dict(
            (
                await self.db.execute(
                    select(Schedule.class_id, func.min(Schedule.starts_at))
                    .where(
                        Schedule.class_id.in_(taught),
                        Schedule.course_id.in_(my_courses),
                        Schedule.starts_at >= datetime.now(timezone.utc),
                    )
                    .group_by(Schedule.class_id)
                )
            ).all()
        )
        items = []
        for cls in classes:
            nxt = next_session.get(cls.id)
            items.append(
                {
                    "id": str(cls.id), "code": cls.code, "name": cls.name, "faculty": cls.faculty,
                    "cohortYear": cls.cohort_year, "studentCount": sizes.get(cls.id, 0),
                    "courses": [_course_ref(c) for c in sorted(taught[cls.id].values(), key=lambda c: c.code)],
                    "nextSessionAt": nxt.isoformat() if nxt else None,
                }
            )
        items.sort(key=lambda x: x["code"])
        return {"items": items}

    async def export_class(self, user: AuthenticatedUser, class_id: str):
        """CSV mã + họ tên học viên của lớp mình dạy (không có email / điện thoại)."""
        detail = await self.class_detail(user, class_id)
        rows = [[s["studentCode"], s["fullName"]] for s in detail["students"]]
        return csv_response(f"lop-{detail['class']['code']}.csv", ["ma_hv", "ho_ten"], rows)

    async def class_detail(self, user: AuthenticatedUser, class_id: str) -> dict:
        try:
            clid = uuid.UUID(class_id)
        except ValueError:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lớp"}) from None
        taught = await self._taught(user, clid)
        cls = await self.db.get(StudyClass, clid)
        # Lớp không thuộc phạm vi của mình trả 404 như lớp không tồn tại (không lộ danh mục lớp).
        if cls is None or clid not in taught:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy lớp"})

        course_ids = list(taught[clid])
        students = (
            await self.db.execute(
                select(StudentProfile.student_code, User.full_name)
                .join(User, User.id == StudentProfile.user_id)
                .where(StudentProfile.class_id == clid)
                .order_by(StudentProfile.student_code.asc())
            )
        ).all()
        now = datetime.now(timezone.utc)
        sessions = (
            await self.db.execute(
                select(Schedule)
                .where(Schedule.class_id == clid, Schedule.course_id.in_(course_ids), Schedule.starts_at >= now)
                .order_by(Schedule.starts_at.asc())
                .limit(5)
            )
        ).scalars().all()
        sections = (
            await self.db.execute(
                select(Schedule.course_id, Schedule.academic_year, Schedule.semester)
                .where(Schedule.class_id == clid, Schedule.course_id.in_(course_ids))
                .distinct()
            )
        ).all()
        return {
            "class": {
                "id": str(cls.id), "code": cls.code, "name": cls.name, "faculty": cls.faculty, "cohortYear": cls.cohort_year,
            },
            "courses": [_course_ref(c) for c in sorted(taught[clid].values(), key=lambda c: c.code)],
            "students": [{"studentCode": code, "fullName": name} for code, name in students],
            "upcoming": [
                {
                    "id": str(s.id), "courseId": str(s.course_id), "courseCode": taught[clid][s.course_id].code,
                    "courseName": taught[clid][s.course_id].name, "startsAt": s.starts_at.isoformat(),
                    "startPeriod": s.start_period, "endPeriod": s.end_period, "room": s.room, "building": s.building,
                }
                for s in sessions
            ],
            "sections": sorted(
                [{"courseId": str(cid), "academicYear": y, "semester": sem} for cid, y, sem in sections],
                key=lambda x: (x["academicYear"], x["semester"]), reverse=True,
            ),
        }
