"""Port of the (deleted) NestJS `forms.controller.ts` — three route groups
mounted from one router module: `/signatures` (no role restriction —
approvers must register a signature too), `/form-templates` (read-only,
any authed user), `/submissions` (`STUDENT` only).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, rate_limit, require_roles
from app.models.enums import RoleCode, SubmissionStatus
from app.schemas.forms import CreateSubmissionDto, SignSubmissionDto, UpdateSubmissionDto
from app.services.forms.forms_service import FormsService
from app.services.forms.signatures_service import SignaturesService

router = APIRouter(tags=["forms"])

_SIGNATURE_MAX_BYTES = 2 * 1024 * 1024


def _parse_uuid4(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail={"message": "id không hợp lệ"})
    return str(parsed)


def _sign_rate_limit():
    return rate_limit("form_sign", 5)


# ------------------------------------------------------------- signatures

@router.post("/signatures")
async def register_signature(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    if len(data) > _SIGNATURE_MAX_BYTES:
        raise HTTPException(status_code=400, detail={"message": "Chữ ký vượt quá 2MB", "code": "FILE_TOO_LARGE"})
    return await SignaturesService(db).register(
        user_id=user.id, file_bytes=data, original_filename=file.filename or "signature.png",
    )


@router.get("/signatures/me")
async def my_signature(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await SignaturesService(db).get_my_signature(user.id)


@router.get("/signatures/me/image")
async def my_signature_image(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = SignaturesService(db)
    sig = await service.get_active_for_user(user.id)
    if not sig:
        raise HTTPException(status_code=404, detail={"message": "Bạn chưa đăng ký chữ ký điện tử"})
    data = service.read_image_bytes(sig)
    return Response(content=data, media_type=sig.mime_type, headers={"Cache-Control": "private, no-store"})


# ---------------------------------------------------------- form templates

@router.get("/form-templates")
async def list_templates(_user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await FormsService(db).list_templates()


@router.get("/form-templates/{code}")
async def get_template(
    code: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await FormsService(db).get_template(code, user)


# --------------------------------------------------------------------------------------------
# submissions — STUDENT only

_student_only = Depends(require_roles(RoleCode.STUDENT.value))


@router.post("/submissions", dependencies=[_student_only])
async def create_submission(
    dto: CreateSubmissionDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FormsService(db).create(dto, user, request)


@router.get("/submissions", dependencies=[_student_only])
async def list_submissions(
    status_: SubmissionStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await FormsService(db).list(user, status_=status_, page=page, page_size=page_size)


@router.get("/submissions/{id}", dependencies=[_student_only])
async def get_submission(id: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    id = _parse_uuid4(id)
    return await FormsService(db).get(id, user)


@router.patch("/submissions/{id}", dependencies=[_student_only])
async def update_submission(
    id: str, dto: UpdateSubmissionDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await FormsService(db).update(id, dto, user, request)


@router.delete("/submissions/{id}", dependencies=[_student_only])
async def delete_submission(
    id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await FormsService(db).remove(id, user, request)


@router.post("/submissions/{id}/sign", dependencies=[_student_only, Depends(_sign_rate_limit())])
async def sign_submission(
    id: str, dto: SignSubmissionDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await FormsService(db).sign(id, dto.pin, user, request)


@router.post("/submissions/{id}/submit", dependencies=[_student_only])
async def submit_submission(
    id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await FormsService(db).submit(id, user, request)


@router.get("/submissions/{id}/verify", dependencies=[_student_only])
async def verify_submission(id: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    id = _parse_uuid4(id)
    return await FormsService(db).verify(id, user)


@router.post("/submissions/{id}/render", dependencies=[_student_only])
async def render_submission(
    id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await FormsService(db).render(id, user, request)


@router.get("/submissions/{id}/file", dependencies=[_student_only])
async def submission_file(
    id: str, ban: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    abs_path, filename = await FormsService(db).file_of(id, user, ban)
    return FileResponse(
        abs_path, filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
