"""Request DTOs for forms/approvals/signatures. Port of (the deleted)
`dto/forms.dto.ts`. Response shapes are plain dicts built by hand in the
service layer, same convention as `documents_service.py`/`chat_service.py`
in this codebase — not modeled as Pydantic response classes.
"""

from __future__ import annotations

from pydantic import Field

from app.models.enums import ApprovalActionType, SubmissionStatus
from app.schemas.base import CamelModel


class CreateSubmissionDto(CamelModel):
    template_code: str = Field(..., min_length=1, max_length=100)
    form_data: dict = Field(default_factory=dict)


class UpdateSubmissionDto(CamelModel):
    form_data: dict = Field(default_factory=dict)


class SignSubmissionDto(CamelModel):
    pin: str = Field(..., min_length=4, max_length=32)


class ApprovalActionDto(CamelModel):
    action: ApprovalActionType
    comment: str | None = Field(default=None, max_length=1000)
    pin: str | None = Field(default=None, min_length=4, max_length=32)


class ListSubmissionsQuery(CamelModel):
    status: SubmissionStatus | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
