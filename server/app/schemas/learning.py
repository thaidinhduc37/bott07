"""DTO cho /learning — ôn tập trắc nghiệm từ giáo trình."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.base import CamelModel


class CreateQuizDto(CamelModel):
    # "bank" = rút từ ngân hàng câu hỏi của giảng viên (bắt buộc có môn, chủ đề tùy chọn); "ai" = sinh từ giáo trình.
    source: Literal["ai", "bank"] = "ai"
    topic: str = Field(default="", max_length=300)
    course_id: str | None = None
    n_questions: int = Field(default=5, ge=3, le=10)
    # Trộn thêm tối đa 3 câu sai đã đến hạn ôn của cùng môn.
    include_review: bool = True

    @field_validator("topic", mode="before")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _topic_for_ai(self) -> "CreateQuizDto":
        if self.source == "ai" and len(self.topic) < 3:
            raise ValueError("Chủ đề cần ít nhất 3 ký tự")
        if self.source == "bank" and not self.course_id:
            raise ValueError("Chọn môn học để ôn từ ngân hàng câu hỏi")
        return self


class CreateReviewDto(CamelModel):
    course_id: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class AnswerDto(CamelModel):
    question_id: str
    # None = bỏ trống, tính là sai.
    selected_index: int | None = Field(default=None, ge=0, le=9)
    # Câu nhiều đáp án đúng: các lựa chọn đã tick (thay cho `selected_index`).
    selected_indexes: list[int] | None = Field(default=None, max_length=10)


class SubmitQuizDto(CamelModel):
    answers: list[AnswerDto] = Field(default_factory=list, max_length=30)
