"""Khoa — thực thể, trưởng khoa, giảng viên thuộc khoa, phân công môn.

Route tĩnh (`/lecturer-candidates`, `/head-candidates`) khai báo TRƯỚC `/{faculty_id}` để không bị bắt nhầm.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode
from app.schemas.faculty import AssignCourseLecturerDto, CreateFacultyDto, UpdateFacultyDto
from app.services.faculty_service import FacultyService

router = APIRouter(prefix="/faculties", tags=["faculties"])

_MANAGERS = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value)
_READERS = (*_MANAGERS, RoleCode.DEPARTMENT_HEAD.value)


@router.get("", dependencies=[Depends(require_roles(*_READERS))])
async def list_faculties(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await FacultyService(db).list(user)


@router.get("/lecturer-candidates", dependencies=[Depends(require_roles(*_READERS))])
async def lecturer_candidates(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await FacultyService(db).lecturer_candidates(user)


@router.get("/head-candidates", dependencies=[Depends(require_roles(*_MANAGERS))])
async def head_candidates(db: AsyncSession = Depends(get_db)):
    return await FacultyService(db).head_candidates()


@router.post("", dependencies=[Depends(require_roles(*_MANAGERS))])
async def create_faculty(
    dto: CreateFacultyDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FacultyService(db).create(dto, user, request)


@router.patch("/{faculty_id}", dependencies=[Depends(require_roles(*_MANAGERS))])
async def update_faculty(
    faculty_id: str, dto: UpdateFacultyDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FacultyService(db).update(faculty_id, dto, user, request)


@router.delete("/{faculty_id}", dependencies=[Depends(require_roles(*_MANAGERS))])
async def delete_faculty(
    faculty_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FacultyService(db).delete(faculty_id, user, request)


@router.get("/{faculty_id}/overview", dependencies=[Depends(require_roles(*_READERS))])
async def faculty_overview(
    faculty_id: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FacultyService(db).overview(faculty_id, user)


@router.put("/{faculty_id}/lecturers/{user_id}", dependencies=[Depends(require_roles(*_READERS))])
async def add_lecturer(
    faculty_id: str, user_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FacultyService(db).add_lecturer(faculty_id, user_id, user, request)


@router.delete("/{faculty_id}/lecturers/{user_id}", dependencies=[Depends(require_roles(*_READERS))])
async def remove_lecturer(
    faculty_id: str, user_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FacultyService(db).remove_lecturer(faculty_id, user_id, user, request)


@router.put("/{faculty_id}/courses/{course_id}", dependencies=[Depends(require_roles(*_READERS))])
async def assign_course_lecturer(
    faculty_id: str, course_id: str, dto: AssignCourseLecturerDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FacultyService(db).assign_course_lecturer(faculty_id, course_id, dto, user, request)
