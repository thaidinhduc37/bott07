"""Request DTOs cho danh mục phòng. Response là dict dựng tay trong service."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import CamelModel


class CreateRoomDto(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    building: str | None = Field(default=None, max_length=100)
    capacity: int | None = Field(default=None, ge=1, le=2000)
    kind: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=300)


class UpdateRoomDto(CamelModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    # `building`, `capacity`, `kind`, `note` cho phép `null` để xóa.
    building: str | None = Field(default=None, max_length=100)
    capacity: int | None = Field(default=None, ge=1, le=2000)
    kind: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=300)
    is_active: bool | None = None
