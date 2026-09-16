"""Port of `chat/dto/chat.dto.ts` (AskDto, ListConversationsDto only — Phase 2
scope). Response shapes are intentionally NOT modeled as Pydantic response
models: `ChatService.present_message()` builds plain dicts by hand so the
documented casing quirk (camelCase message fields, but snake_case fields
*inside* `retrievedChunks`, passed straight through from rag-service's JSON)
is reproduced exactly. Wrapping that in a `CamelModel` would re-alias the
inner snake_case keys too and silently "fix" a quirk the client depends on.
"""

from __future__ import annotations

import uuid

from pydantic import Field, field_validator

from app.models.enums import ChatMode
from app.schemas.base import CamelModel


def _validate_uuid4(v: str | None) -> str | None:
    if v is None:
        return v
    try:
        uuid.UUID(v, version=4)
    except ValueError:
        raise ValueError("phải là UUID hợp lệ")
    return v


class AskDto(CamelModel):
    question: str = Field(..., min_length=3, max_length=2000)
    mode: ChatMode
    # Continue an existing conversation. Empty -> a new conversation is created.
    conversation_id: str | None = None
    # Filter by course. Only meaningful for GIAOTRINH mode.
    course_id: str | None = None

    @field_validator("question", mode="before")
    @classmethod
    def _trim(cls, v: str) -> str:
        # Trim BEFORE length validation (mirrors class-transformer's
        # `@Transform` running before class-validator's `@MinLength` in the
        # reference DTO) — otherwise "  ab  " would pass min_length=3 on the
        # untrimmed value and then get stored trimmed to 2 chars.
        return v.strip() if isinstance(v, str) else v

    @field_validator("conversation_id", "course_id")
    @classmethod
    def _uuid4(cls, v: str | None) -> str | None:
        return _validate_uuid4(v)
