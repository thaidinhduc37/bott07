"""Tài liệu nguồn (`/documents`). Học viên không dùng đường này: hỏi đáp của học viên đi qua `/chat`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_db, require_roles
from app.models.enums import DocumentType, RoleCode
from app.schemas.documents import UploadDocumentDto
from app.services.documents.documents_service import DocumentsService

# Same role gate as every route below (via the per-route `require_roles`
# dependency that also yields the AuthenticatedUser) — kept as one constant so
# the three roles are declared in exactly one place.
_MANAGER_ROLES = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value, RoleCode.LECTURER.value)

router = APIRouter(prefix="/documents", tags=["documents"])


def _parse_uuid4(value: str) -> str:
    try:
        parsed = uuid.UUID(value, version=4)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": "id không hợp lệ"}) from exc
    return str(parsed)


@router.post("")
async def upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: DocumentType = Form(..., alias="documentType"),
    course_id: str | None = Form(default=None, alias="courseId"),
    reference_no: str | None = Form(default=None, alias="referenceNo"),
    issued_at: str | None = Form(default=None, alias="issuedAt"),
    user: AuthenticatedUser = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    dto = UploadDocumentDto(
        title=title,
        documentType=document_type,
        courseId=course_id,
        referenceNo=reference_no,
        issuedAt=issued_at,
    )
    data = await file.read()
    return await DocumentsService(db).upload(
        file_bytes=data,
        original_filename=file.filename or "upload",
        dto=dto,
        user=user,
        request=request,
        background_tasks=background_tasks,
    )


@router.get("")
async def list_documents(
    document_type: DocumentType | None = Query(default=None, alias="documentType"),
    course_id: str | None = Query(default=None, alias="courseId"),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, alias="pageSize"),
    user: AuthenticatedUser = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await DocumentsService(db).list(
        document_type=document_type, course_id=course_id, search=search, page=page, page_size=page_size, user=user
    )


@router.get("/index-status")
async def index_status(
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(require_roles(*_MANAGER_ROLES)),
):
    return await DocumentsService(db).index_status()


@router.get("/{id}")
async def find_one(
    id: str,
    user: AuthenticatedUser = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await DocumentsService(db).get(id, user)


@router.post("/{id}/reindex")
async def reindex(
    id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await DocumentsService(db).reindex(id, user, request, background_tasks)


@router.delete("/{id}")
async def remove(
    id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await DocumentsService(db).remove(id, user, request)
