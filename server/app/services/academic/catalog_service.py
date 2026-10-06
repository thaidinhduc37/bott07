"""Catalog: CRUD Lớp / Môn học (gán giảng viên) + gán học viên vào lớp.

Quy tắc giữ nguyên từ các service khác:

- Mọi ghi đều kèm audit trong cùng transaction (`self.audit.log` rồi `commit`).
- Không lazy-load ngoài `await`: quan hệ cần dùng đều `selectinload` hoặc truy vấn tường minh.
- Lỗi chuẩn `HTTPException(detail={"message": ..., "code": ...})`.
- Id không tồn tại → 404 (không 500).
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import Faculty
from app.services.accounts.audit_service import AuditService

from app.services.academic.catalog_classes import ClassesMixin
from app.services.academic.catalog_courses import CoursesMixin
from app.services.academic.catalog_students import StudentsMixin


class CatalogService(ClassesMixin, CoursesMixin, StudentsMixin):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def _faculty_names(self) -> dict:
        """id → tên khoa, một truy vấn cho cả danh sách."""
        return {fid: name for fid, name in (await self.db.execute(select(Faculty.id, Faculty.name))).all()}

    async def _resolve_faculty(self, faculty_id: str | None) -> Faculty | None:
        """`facultyId` phải là khoa có thật; None = không xếp khoa."""
        if faculty_id is None:
            return None
        try:
            fid = uuid.UUID(faculty_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise HTTPException(status_code=400, detail={"message": "Khoa không hợp lệ", "code": "INVALID_FACULTY"}) from exc
        row = await self.db.get(Faculty, fid)
        if not row:
            raise HTTPException(status_code=400, detail={"message": "Khoa không hợp lệ", "code": "INVALID_FACULTY"})
        return row
