from __future__ import annotations

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import CamelModel, CamelReadModel


class LoginRequest(CamelModel):
    email: EmailStr = Field(max_length=200)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v):
        if isinstance(v, str):
            return v.strip().lower()
        return v


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

    @field_validator("new_password")
    @classmethod
    def _must_have_letter_and_digit(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError("Mật khẩu mới phải có ít nhất một chữ cái")
        if not any(c.isdigit() for c in v):
            raise ValueError("Mật khẩu mới phải có ít nhất một chữ số")
        return v


class SetSignaturePinRequest(CamelModel):
    password: str = Field(min_length=1, max_length=200)
    pin: str = Field(pattern=r"^\d{6}$")


class AuthenticatedUserOut(CamelReadModel):
    id: str
    email: str
    full_name: str
    roles: list[str]
    must_set_signature_pin: bool


class LoginResponse(CamelReadModel):
    user: AuthenticatedUserOut
    access_token: str
    expires_in: int


class RefreshResponse(CamelReadModel):
    access_token: str
    expires_in: int


class MessageResponse(CamelReadModel):
    message: str
