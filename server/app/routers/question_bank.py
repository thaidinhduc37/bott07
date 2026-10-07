"""Ngân hàng câu hỏi (giảng viên / quản lý): xem, nhập GIFT/CSV, xóa. Phạm vi môn kiểm tra trong service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode
from app.services.learning.question_bank_service import QuestionBankService

router = APIRouter(prefix="/question-bank", tags=["question-bank"])

_STAFF = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value, RoleCode.LECTURER.value)
_IMPORT_MAX_BYTES = 2 * 1024 * 1024


@router.get("/courses", dependencies=[Depends(require_roles(*_STAFF))])
async def courses(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await QuestionBankService(db).courses(user)


@router.get("/questions", dependencies=[Depends(require_roles(*_STAFF))])
async def list_questions(
    course_id: str = Query(..., alias="courseId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await QuestionBankService(db).list_questions(user, course_id, page, page_size)


@router.delete("/questions/{question_id}", dependencies=[Depends(require_roles(*_STAFF))])
async def delete_question(
    question_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await QuestionBankService(db).delete_question(user, question_id, request)


@router.post("/import", dependencies=[Depends(require_roles(*_STAFF))])
async def import_questions(
    request: Request,
    course_id: str = Query(..., alias="courseId"),
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False, alias="dryRun"),
    fmt: str | None = Query(default=None, alias="format", pattern="^(gift|csv)$"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    if len(data) > _IMPORT_MAX_BYTES:
        raise HTTPException(status_code=400, detail={"message": "Tệp vượt quá 2MB", "code": "FILE_TOO_LARGE"})
    # Không chỉ định thì đoán theo đuôi tệp: .csv → CSV, còn lại → GIFT.
    fmt = fmt or ("csv" if (file.filename or "").lower().endswith(".csv") else "gift")
    return await QuestionBankService(db).import_file(
        user, course_id, content=data, filename=file.filename, fmt=fmt, dry_run=dry_run, request=request,
    )
