"""Điểm học phần: học viên xem; giảng viên nhập điểm môn mình phụ trách; phòng đào tạo nhập CSV."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode
from app.schemas.base import CamelModel
from app.services.academic.grades_service import GradesService

router = APIRouter(prefix="/grades", tags=["grades"])

_GRADERS = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value, RoleCode.LECTURER.value)
_MANAGERS = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value)
_IMPORT_MAX_BYTES = 2 * 1024 * 1024


class ScoreItem(CamelModel):
    student_id: str
    practice: float | None = None
    process: float | None = None
    midterm: float | None = None
    final_exam: float | None = None
    total: float | None = None
    note: str | None = Field(default=None, max_length=300)


class SaveScoresDto(CamelModel):
    course_id: str
    academic_year: str = Field(..., min_length=1, max_length=20)
    semester: str = Field(..., min_length=1, max_length=20)
    items: list[ScoreItem] = Field(..., min_length=1, max_length=500)


@router.get("/me", dependencies=[Depends(require_roles(RoleCode.STUDENT.value))])
async def my_results(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await GradesService(db).my_results(user.id)


@router.get("/sections", dependencies=[Depends(require_roles(*_GRADERS))])
async def sections(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await GradesService(db).sections(user)


@router.get("/sections/roster", dependencies=[Depends(require_roles(*_GRADERS))])
async def roster(
    course_id: str = Query(..., alias="courseId"),
    class_id: str = Query(..., alias="classId"),
    academic_year: str = Query(..., alias="academicYear"),
    semester: str = Query(...),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GradesService(db).roster(
        user, course_id=course_id, class_id=class_id, year=academic_year, semester=semester,
    )


@router.put("/sections/scores", dependencies=[Depends(require_roles(*_GRADERS))])
async def save_scores(
    dto: SaveScoresDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await GradesService(db).save_scores(
        user, course_id=dto.course_id, year=dto.academic_year, semester=dto.semester,
        items=[i.model_dump() | {"finalExam": i.final_exam, "studentId": i.student_id} for i in dto.items],
        request=request,
    )


@router.post("/import", dependencies=[Depends(require_roles(*_MANAGERS))])
async def import_grades(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False, alias="dryRun"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    if len(data) > _IMPORT_MAX_BYTES:
        raise HTTPException(status_code=400, detail={"message": "Tệp vượt quá 2MB", "code": "FILE_TOO_LARGE"})
    return await GradesService(db).import_csv(user, content=data, filename=file.filename, dry_run=dry_run, request=request)
