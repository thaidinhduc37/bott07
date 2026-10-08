"""DTO tải tài liệu. Tải lên là multipart (các trường vào router dưới dạng `Form(...)`) nên `UploadDocumentDto` chỉ kiểm tra và
chuẩn hóa các trường không phải tệp."""

from __future__ import annotations

from pydantic import Field, field_validator

from app.models.enums import DocumentType
from app.schemas.base import CamelModel


class UploadDocumentDto(CamelModel):
    title: str = Field(..., max_length=300)
    document_type: DocumentType
    course_id: str | None = None
    reference_no: str | None = Field(default=None, max_length=100)
    issued_at: str | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _trim_title(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v
