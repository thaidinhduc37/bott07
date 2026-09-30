"""DTO cho /learning/notes — sổ tay học tập."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import CamelModel


class NoteFromSourceDto(CamelModel):
    # id tin nhắn trả lời (from-chat) hoặc id câu trắc nghiệm (from-quiz).
    source_id: str
    # Hội thoại không lưu môn học, nên client gửi kèm môn đang chọn nếu có.
    course_id: str | None = None
    note: str | None = Field(default=None, max_length=4000)


class CreateNoteDto(CamelModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1, max_length=20000)
    course_id: str | None = None


class UpdateNoteDto(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    note: str | None = Field(default=None, max_length=4000)
    pinned: bool | None = None
