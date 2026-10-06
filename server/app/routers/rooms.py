"""Danh mục phòng học. Đọc: quản trị, quản lý đào tạo, giảng viên, lãnh đạo khoa. Ghi: quản trị + quản lý đào tạo."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode
from app.schemas.rooms import CreateRoomDto, UpdateRoomDto
from app.services.academic.rooms_service import RoomsService

router = APIRouter(prefix="/rooms", tags=["rooms"])

_MANAGERS = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value)
_READERS = (*_MANAGERS, RoleCode.LECTURER.value, RoleCode.DEPARTMENT_HEAD.value)


@router.get("", dependencies=[Depends(require_roles(*_READERS))])
async def list_rooms(
    active_only: bool = Query(default=False, alias="activeOnly"),
    search: str | None = Query(default=None, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    return await RoomsService(db).list(active_only=active_only, search=search)


@router.post("", dependencies=[Depends(require_roles(*_MANAGERS))])
async def create_room(
    dto: CreateRoomDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await RoomsService(db).create(dto, user, request)


@router.get("/{room_id}/timetable", dependencies=[Depends(require_roles(*_READERS))])
async def room_timetable(
    room_id: str,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await RoomsService(db).timetable(room_id, from_, to)


@router.patch("/{room_id}", dependencies=[Depends(require_roles(*_MANAGERS))])
async def update_room(
    room_id: str, dto: UpdateRoomDto, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await RoomsService(db).update(room_id, dto, user, request)


@router.delete("/{room_id}", dependencies=[Depends(require_roles(*_MANAGERS))])
async def delete_room(
    room_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await RoomsService(db).delete(room_id, user, request)
