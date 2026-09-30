"""Request DTOs cho module catalog (Lớp / Môn học / Học viên).

Response shapes là dict dựng tay trong service (quy ước chung của codebase).
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import CamelModel


class CreateClassDto(CamelModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=200)
    faculty: str | None = Field(default=None, max_length=200)
    faculty_id: str | None = None
    cohort_year: int | None = Field(default=None, ge=1900, le=2200)


class UpdateClassDto(CamelModel):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    # `faculty`/`cohortYear` cho phép `null` để xóa giá trị hiện có.
    faculty: str | None = Field(default=None, max_length=200)
    faculty_id: str | None = None
    cohort_year: int | None = Field(default=None, ge=1900, le=2200)


class CreateCourseDto(CamelModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=200)
    credits: int = Field(..., ge=1, le=20)
    description: str | None = Field(default=None, max_length=2000)
    lecturer_id: str | None = None
    faculty_id: str | None = None


class UpdateCourseDto(CamelModel):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    credits: int | None = Field(default=None, ge=1, le=20)
    description: str | None = Field(default=None, max_length=2000)
    lecturer_id: str | None = None
    faculty_id: str | None = None


class SetStudentClassDto(CamelModel):
    class_id: str | None = None


class AssignStudentsDto(CamelModel):
    class_id: str
    user_ids: list[str] = Field(..., min_length=1, max_length=200)
