from __future__ import annotations

from datetime import date, datetime

from pydantic import EmailStr, Field, field_validator

from app.models.enums import RoleCode, UserStatus
from app.schemas.base import CamelModel, CamelReadModel


class UpdateMyProfileRequest(CamelModel):
    phone: str | None = Field(default=None, pattern=r"^0\d{9,10}$")
    address: str | None = Field(default=None, max_length=300)
    place_of_birth: str | None = Field(default=None, max_length=100)

    @field_validator("address", mode="before")
    @classmethod
    def _trim_address(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class CreateUserRequest(CamelModel):
    email: EmailStr = Field(max_length=200)
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=8, max_length=200)
    phone: str | None = Field(default=None, pattern=r"^0\d{9,10}$")
    roles: list[RoleCode]
    student_code: str | None = Field(default=None, max_length=30)
    class_code: str | None = None
    cohort: str | None = None
    training_system: str | None = None
    # Khoa của giảng viên / lãnh đạo khoa (học viên thuộc khoa qua lớp nên bỏ qua trường này).
    faculty_id: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v):
        if isinstance(v, str):
            return v.strip().lower()
        return v


class UpdateUserStatusRequest(CamelModel):
    status: UserStatus
    reason: str | None = Field(default=None, max_length=300)


class UpdateUserRolesRequest(CamelModel):
    roles: list[RoleCode]


class ListUsersQuery(CamelModel):
    search: str | None = Field(default=None, max_length=100)
    role: RoleCode | None = None
    status: UserStatus | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ------------------------------------------------------------------- output

class RoleOut(CamelReadModel):
    code: RoleCode
    name: str


class StudyClassOut(CamelReadModel):
    id: str
    code: str
    name: str
    faculty: str | None = None


class StudentProfileMeOut(CamelReadModel):
    student_code: str
    date_of_birth: date | None = None
    place_of_birth: str | None = None
    gender: str | None = None
    address: str | None = None
    cohort: str | None = None
    training_system: str | None = None
    enroll_year: int | None = None
    study_class: StudyClassOut | None = None


class SignatureOut(CamelReadModel):
    id: str
    created_at: datetime
    mime_type: str


class MyProfileOut(CamelReadModel):
    id: str
    email: str
    full_name: str
    phone: str | None = None
    status: UserStatus
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[RoleCode]
    role_names: list[str]
    has_signature_pin: bool
    has_signature: bool
    student_profile: StudentProfileMeOut | None = None


class AdminUserListItemOut(CamelReadModel):
    id: str
    email: str
    full_name: str
    phone: str | None = None
    status: UserStatus
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[RoleCode]
    student_code: str | None = None
    class_code: str | None = None


class PaginatedUsersOut(CamelReadModel):
    total: int
    page: int
    page_size: int
    items: list[AdminUserListItemOut]


class AuditLogItemUserOut(CamelReadModel):
    id: str
    email: str
    full_name: str


class AuditLogItemOut(CamelReadModel):
    id: str
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    detail: dict | list | str | int | float | bool | None = None
    ip_address: str | None = None
    created_at: datetime
    user: AuditLogItemUserOut | None = None


class PaginatedAuditLogsOut(CamelReadModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogItemOut]
