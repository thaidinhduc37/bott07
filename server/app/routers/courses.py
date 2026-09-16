"""`GET /courses` (Phase 2 — any authed user, minimal fields, backs the
document-upload and chat course-pickers) plus `GET /classes` (Phase 4 —
staff-only, list classes with student/session-count aggregates). Kept in one
file since both are small, read-only, and reference-adjacent
(`courses.controller.ts` + `classes.controller.ts` were two thin sibling
controllers in the original)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.academic import Course, Schedule, StudyClass
from app.models.enums import RoleCode
from app.models.users import StudentProfile, User

router = APIRouter(prefix="/courses", tags=["courses"])
classes_router = APIRouter(prefix="/classes", tags=["classes"])

_STAFF_ROLES = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value, RoleCode.LECTURER.value)


@router.get("")
async def list_courses(db: AsyncSession = Depends(get_db), _user: AuthenticatedUser = Depends(get_current_user)):
    stmt = select(Course, User.full_name).outerjoin(User, User.id == Course.lecturer_id).order_by(Course.code.asc())
    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "id": str(c.id), "code": c.code, "name": c.name, "credits": c.credits,
                "description": c.description,
                "lecturer": {"id": str(c.lecturer_id), "fullName": lecturer_name} if c.lecturer_id else None,
            }
            for c, lecturer_name in rows
        ]
    }


@classes_router.get("", dependencies=[Depends(require_roles(*_STAFF_ROLES))])
async def list_classes(db: AsyncSession = Depends(get_db)):
    student_count_stmt = (
        select(StudentProfile.class_id, func.count()).group_by(StudentProfile.class_id)
    )
    student_counts = {cid: n for cid, n in (await db.execute(student_count_stmt)).all() if cid is not None}

    session_count_stmt = select(Schedule.class_id, func.count()).group_by(Schedule.class_id)
    session_counts = {cid: n for cid, n in (await db.execute(session_count_stmt)).all()}

    rows = (await db.execute(select(StudyClass).order_by(StudyClass.code.asc()))).scalars().all()
    return {
        "items": [
            {
                "id": str(c.id), "code": c.code, "name": c.name, "faculty": c.faculty, "cohortYear": c.cohort_year,
                "studentCount": student_counts.get(c.id, 0), "sessionCount": session_counts.get(c.id, 0),
            }
            for c in rows
        ]
    }
