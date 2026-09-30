"""DTO cho /learning — ôn tập trắc nghiệm từ giáo trình."""

from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.base import CamelModel


class CreateQuizDto(CamelModel):
    topic: str = Field(..., min_length=3, max_length=300)
    course_id: str | None = None
    n_questions: int = Field(default=5, ge=3, le=10)
    # Trộn thêm tối đa 3 câu sai đã đến hạn ôn của cùng môn.
    include_review: bool = True

    @field_validator("topic", mode="before")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class CreateReviewDto(CamelModel):
    course_id: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class AnswerDto(CamelModel):
    question_id: str
    # None = bỏ trống, tính là sai.
    selected_index: int | None = Field(default=None, ge=0, le=3)


class SubmitQuizDto(CamelModel):
    answers: list[AnswerDto] = Field(default_factory=list, max_length=30)
