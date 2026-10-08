"""Phê duyệt đơn (`/approvals`). Quyền truy cập hoàn toàn theo bước duyệt (người dùng có vai trò khớp một bước của đơn), không có
`require_roles` thô: người duyệt, cán bộ và lãnh đạo khoa dùng chung endpoint, khác nhau ở bước mà vai trò mở ra."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, user_rate_limit
from app.schemas.forms import ApprovalActionDto
from app.services.forms.approvals_service import ApprovalsService

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _parse_uuid4(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": "id không hợp lệ"}) from exc
    return str(parsed)


def _action_rate_limit():
    return user_rate_limit("approval_action", 30)


@router.get("")
async def inbox(
    da_xu_ly: str | None = Query(default=None, alias="daXuLy"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ApprovalsService(db).inbox(user, done=bool(da_xu_ly))


@router.get("/{id}")
async def detail(id: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    id = _parse_uuid4(id)
    return await ApprovalsService(db).detail(id, user)


@router.post("/{id}/action", dependencies=[Depends(_action_rate_limit())])
async def act(
    id: str, dto: ApprovalActionDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    id = _parse_uuid4(id)
    return await ApprovalsService(db).act(
        id, dto.action, comment=dto.comment, pin=dto.pin, user=user, request=request,
    )


@router.get("/{id}/file")
async def file(id: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    id = _parse_uuid4(id)
    abs_path, filename = await ApprovalsService(db).file_of(id, user)
    return FileResponse(
        abs_path, filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
