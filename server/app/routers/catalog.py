"""Catalog: CRUD Lớp / Môn học (gồm gán giảng viên phụ trách) + gán học viên
vào lớp. Mọi endpoint chỉ dành cho ADMIN và ACADEMIC_MANAGER.

Router KHÔNG tự đăng ký — người kiểm soát thêm
`app.include_router(catalog.router, prefix=api_prefix)` vào `main.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthenticatedUser, get_current_user, get_db, require_roles
from app.models.enums import RoleCode
from app.schemas.catalog import (
    AssignStudentsDto,
    CreateClassDto,
    CreateCourseDto,
    SetStudentClassDto,
    UpdateClassDto,
    UpdateCourseDto,
)
from app.services.academic.catalog_service import CatalogService

router = APIRouter(prefix="/catalog", tags=["catalog"])

_MANAGER_ROLES = (RoleCode.ADMIN.value, RoleCode.ACADEMIC_MANAGER.value)


# ------------------------------------------------------------------- classes

@router.get("/classes", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def list_classes(
    db: AsyncSession = Depends(get_db), _user: AuthenticatedUser = Depends(get_current_user)
):
    return await CatalogService(db).list_classes()


@router.post("/classes", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def create_class(
    dto: CreateClassDto,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).create_class(dto, user, request)


@router.patch("/classes/{id}", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def update_class(
    id: str,
    dto: UpdateClassDto,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).update_class(id, dto, user, request)


@router.delete("/classes/{id}", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def delete_class(
    id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).delete_class(id, user, request)


# ------------------------------------------------------------------- courses

@router.get("/courses", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def list_courses(
    db: AsyncSession = Depends(get_db), _user: AuthenticatedUser = Depends(get_current_user)
):
    return await CatalogService(db).list_courses()


@router.post("/courses", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def create_course(
    dto: CreateCourseDto,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).create_course(dto, user, request)


@router.patch("/courses/{id}", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def update_course(
    id: str,
    dto: UpdateCourseDto,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).update_course(id, dto, user, request)


@router.delete("/courses/{id}", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def delete_course(
    id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).delete_course(id, user, request)


# ---------------------------------------------------------------- lecturers

@router.get("/lecturers", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def list_lecturers(
    db: AsyncSession = Depends(get_db), _user: AuthenticatedUser = Depends(get_current_user)
):
    return await CatalogService(db).list_lecturers()


# ------------------------------------------------------------------ students

@router.get("/students", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def list_students(
    class_id: str | None = Query(default=None, alias="classId"),
    search: str | None = Query(default=None, max_length=100),
    unassigned: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(get_current_user),
):
    return await CatalogService(db).list_students(
        class_id=class_id, search=search, unassigned=unassigned, page=page, page_size=page_size,
    )


@router.put("/students/{user_id}/class", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def set_student_class(
    user_id: str,
    dto: SetStudentClassDto,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).set_student_class(user_id, dto, user, request)


@router.post("/students/assign-class", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def assign_students(
    dto: AssignStudentsDto,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService(db).assign_students(dto, user, request)


_IMPORT_MAX_BYTES = 2 * 1024 * 1024


@router.get("/students/export", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def export_students(
    class_id: str | None = Query(default=None, alias="classId"),
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(get_current_user),
):
    """CSV danh sách học viên (một lớp hoặc tất cả) — cùng cột với tệp nhập."""
    return await CatalogService(db).export_students(class_id=class_id)


@router.post("/students/import", dependencies=[Depends(require_roles(*_MANAGER_ROLES))])
async def import_students(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False, alias="dryRun"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Nhập danh sách học viên từ CSV (tạo tài khoản mới, cập nhật lớp / họ tên). Xem `catalog_import.py`."""
    data = await file.read()
    if len(data) > _IMPORT_MAX_BYTES:
        raise HTTPException(status_code=400, detail={"message": "Tệp vượt quá 2MB", "code": "FILE_TOO_LARGE"})
    return await CatalogService(db).import_students(
        user, content=data, filename=file.filename, dry_run=dry_run, request=request,
    )
