"""Lịch học và lịch thi (`/schedules`). Route của học viên (`/me`, `/me/courses`) không nhận tham số lớp: lớp luôn lấy từ
`StudentProfile` của người gọi để chống IDOR."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode
from app.schemas.schedules import (
    CreateExamDto,
    CreateScheduleDto,
    ImportScheduleDto,
    LecturerNoteDto,
    UpdateExamDto,
    UpdateScheduleDto,
)
from app.services.academic.terms_service import TermsService
from app.services.academic.schedules_service import SchedulesService

router = APIRouter(prefix="/schedules", tags=["schedules"])

_STAFF_ROLES = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value, RoleCode.LECTURER.value)
_MANAGER_ROLES = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value)
_IMPORT_MAX_BYTES = 5 * 1024 * 1024


def _parse_uuid4(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": "id không hợp lệ"}) from exc
    return str(parsed)


@router.get("/me")
async def my_timetable(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    include_exams: bool = Query(default=True, alias="includeExams"),
    course_id: str | None = Query(default=None, alias="courseId"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await SchedulesService(db).my_timetable(
        user.id, from_=from_, to=to, include_exams=include_exams, course_id=course_id,
    )


@router.get("/me/terms")
async def my_terms(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await TermsService(db).my_terms(user.id)


@router.get("/me/enrollments")
async def my_enrollments(
    academic_year: str | None = Query(default=None, alias="academicYear"),
    semester: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TermsService(db).my_enrollments(user.id, academic_year, semester)


@router.get("/me/exam-term")
async def my_exam_term(
    academic_year: str | None = Query(default=None, alias="academicYear"),
    semester: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TermsService(db).my_exams(user.id, academic_year, semester)


@router.get("/me/courses")
async def my_courses(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await SchedulesService(db).my_courses(user.id)


@router.get("/me/exams")
async def my_exams(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await SchedulesService(db).exams_in_range(user.id, from_=from_, to=to)


@router.get("/teaching", dependencies=[Depends(require_roles(*_STAFF_ROLES))])
async def teaching_timetable(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    class_id: str | None = Query(default=None, alias="classId"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lịch giảng dạy: buổi học + ca thi mà người gọi được ghi yêu cầu."""
    return await SchedulesService(db).teaching(user, from_=from_, to=to, class_id=class_id)


@router.put("/sessions/{id}/lecturer-note", dependencies=[Depends(require_roles(*_STAFF_ROLES))])
async def set_session_note(
    id: str, dto: LecturerNoteDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await SchedulesService(db).set_lecturer_note(
        "SESSION", id, dto.note, notify=dto.notify, user=user, request=request,
    )


@router.put("/exams/{id}/lecturer-note", dependencies=[Depends(require_roles(*_STAFF_ROLES))])
async def set_exam_note(
    id: str, dto: LecturerNoteDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await SchedulesService(db).set_lecturer_note(
        "EXAM", id, dto.note, notify=dto.notify, user=user, request=request,
    )


@router.get("", dependencies=[Depends(require_roles(*_STAFF_ROLES))])
async def list_schedules(
    class_id: str | None = Query(default=None, alias="classId"),
    class_code: str | None = Query(default=None, alias="classCode"),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    course_id: str | None = Query(default=None, alias="courseId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500, alias="pageSize"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await SchedulesService(db).list(
        user, class_id=class_id, class_code=class_code, from_=from_, to=to, course_id=course_id,
        page=page, page_size=page_size,
    )


@router.post("", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def create_schedule(
    dto: CreateScheduleDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await SchedulesService(db).create(dto, user, request)


@router.post("/import", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def import_schedules(
    request: Request,
    file: UploadFile = File(...),
    class_id: str = Query(..., alias="classId"),
    dry_run: bool = Query(default=False, alias="dryRun"),
    allow_partial: bool = Query(default=False, alias="allowPartial"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ImportScheduleDto(classId=class_id, dryRun=dry_run, allowPartial=allow_partial)  # validate shape
    data = await file.read()
    if len(data) > _IMPORT_MAX_BYTES:
        raise HTTPException(status_code=400, detail={"message": "File vượt quá 5MB", "code": "FILE_TOO_LARGE"})
    return await SchedulesService(db).import_schedules(
        file_bytes=data, filename=file.filename, class_id=class_id, dry_run=dry_run, allow_partial=allow_partial,
        user=user, request=request,
    )


@router.get("/availability", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def availability(
    day: str = Query(..., alias="date"),
    start_time: str = Query(..., alias="startTime"),
    end_time: str = Query(..., alias="endTime"),
    exclude_id: str | None = Query(default=None, alias="excludeId"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phòng / giảng viên nào đang bận trong khoảng giờ của một ngày (VN)."""
    return await SchedulesService(db).availability(
        day=day, start_time=start_time, end_time=end_time, exclude_id=exclude_id,
    )


@router.post("/exams", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def create_exam(
    dto: CreateExamDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await SchedulesService(db).create_exam(dto, user, request)


@router.patch("/exams/{id}", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def update_exam(
    id: str, dto: UpdateExamDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await SchedulesService(db).update_exam(id, dto, user, request)


@router.delete("/exams/{id}", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def delete_exam(
    id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await SchedulesService(db).delete_exam(id, user, request)


@router.patch("/{id}", dependencies=[Depends(require_roles(*_STAFF_ROLES))])
async def update_schedule(
    id: str, dto: UpdateScheduleDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await SchedulesService(db).update(id, dto, user, request)


@router.delete("/{id}", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def delete_schedule(
    id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await SchedulesService(db).remove(id, user, request)
