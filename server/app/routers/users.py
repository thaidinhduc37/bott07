"""Port of `users/users.controller.ts` — three route groups: self-service
`/users/*`, admin `/admin/users/*`, and `/admin/audit-logs`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode, UserStatus
from app.schemas.users import (
    CreateUserRequest,
    UpdateMyProfileRequest,
    UpdateUserRolesRequest,
    UpdateUserStatusRequest,
)
from app.services.accounts.users_service import UsersService

users_router = APIRouter(prefix="/users", tags=["users"])
admin_users_router = APIRouter(prefix="/admin/users", tags=["admin-users"])
admin_audit_router = APIRouter(prefix="/admin/audit-logs", tags=["admin-audit"])


def _validate_uuid(value: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": "id không hợp lệ"}) from exc
    return value


@users_router.get("/me")
async def get_me(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await UsersService(db).get_my_profile(user.id)


@users_router.patch("/me")
async def update_me(
    dto: UpdateMyProfileRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await UsersService(db).update_my_profile(user.id, dto, request)


# ------------------------------------------------------------------- admin

@admin_users_router.get("", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def list_users(
    search: str | None = Query(default=None, max_length=100),
    role: RoleCode | None = Query(default=None),
    status_: UserStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
):
    return await UsersService(db).list_users(search=search, role=role, status_=status_, page=page,
                                              page_size=page_size)


@admin_users_router.post("", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def create_user(
    dto: CreateUserRequest,
    request: Request,
    actor: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await UsersService(db).create_user(dto, actor.id, request)


@admin_users_router.patch("/{user_id}/status", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def update_status(
    user_id: str,
    dto: UpdateUserStatusRequest,
    request: Request,
    actor: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_uuid(user_id)
    return await UsersService(db).update_status(user_id, dto, actor.id, request)


@admin_users_router.put("/{user_id}/roles", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def update_roles(
    user_id: str,
    dto: UpdateUserRolesRequest,
    request: Request,
    actor: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_uuid(user_id)
    return await UsersService(db).update_roles(user_id, dto, actor.id, request)


@admin_audit_router.get("", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, alias="pageSize"),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None, alias="userId"),
    db: AsyncSession = Depends(get_db),
):
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    return await UsersService(db).list_audit_logs(page=page, page_size=page_size, action=action, user_id=user_id)
