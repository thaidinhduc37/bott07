"""Request DTOs cho module Khoa. Response là dict dựng tay trong service (quy ước chung)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import CamelModel


class CreateFacultyDto(CamelModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    head_id: str | None = None


class UpdateFacultyDto(CamelModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    # `headId: null` = bỏ trưởng khoa; vắng = giữ nguyên.
    head_id: str | None = None


class AssignCourseLecturerDto(CamelModel):
    # `null` = bỏ phân công.
    lecturer_id: str | None = None
