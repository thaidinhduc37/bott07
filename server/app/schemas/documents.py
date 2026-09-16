"""Port of `documents/dto/documents.dto.ts`. Upload is multipart (fields come
in as `Form(...)` params in the router, not a JSON body), so `UploadDocumentDto`
here is used only to validate/normalize the non-file fields collected from the
form — mirrors the shape class-validator enforced in the reference DTO.
"""

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
