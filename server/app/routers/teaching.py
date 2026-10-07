"""Lớp của giảng viên (chỉ đọc): các lớp có môn mình phụ trách, danh sách học viên, buổi học sắp tới."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode
from app.services.academic.teaching_service import TeachingService

router = APIRouter(prefix="/teaching", tags=["teaching"])


@router.get("/classes", dependencies=[Depends(require_roles(RoleCode.LECTURER.value))])
async def my_classes(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await TeachingService(db).list_classes(user)


@router.get("/classes/{class_id}", dependencies=[Depends(require_roles(RoleCode.LECTURER.value))])
async def my_class(class_id: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await TeachingService(db).class_detail(user, class_id)


@router.get("/classes/{class_id}/export", dependencies=[Depends(require_roles(RoleCode.LECTURER.value))])
async def export_class(class_id: str, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await TeachingService(db).export_class(user, class_id)
