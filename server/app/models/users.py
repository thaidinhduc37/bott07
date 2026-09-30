from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TIMESTAMPTZ, created_at_col, updated_at_col, uuid_pk
from app.models.enums import RoleCode, UserStatus


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column("password_hash", String, nullable=False)
    full_name: Mapped[str] = mapped_column("full_name", String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="UserStatus", native_enum=True),
        default=UserStatus.ACTIVE,
        nullable=False,
    )
    signature_pin_hash: Mapped[str | None] = mapped_column("signature_pin_hash", String, nullable=True)
    # Khoa của giảng viên / cán bộ (học viên thuộc khoa qua lớp). NULL = chưa xếp khoa.
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(
        "faculty_id", PGUUID(as_uuid=True), ForeignKey("faculties.id", ondelete="SET NULL"), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column("last_login_at", TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    student_profile: Mapped["StudentProfile | None"] = relationship(back_populates="user", uselist=False)
    signatures: Mapped[list["ElectronicSignature"]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user")

    uploaded_documents: Mapped[list["Document"]] = relationship(back_populates="uploaded_by")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    conversations: Mapped[list["ChatConversation"]] = relationship(back_populates="user")
    taught_courses: Mapped[list["Course"]] = relationship(back_populates="lecturer")

    # Forms/approvals (re-added alongside app/models/forms.py).
    submissions: Mapped[list["FormSubmission"]] = relationship(back_populates="owner")
    approval_steps: Mapped[list["ApprovalStep"]] = relationship(back_populates="assignee")
    approval_actions: Mapped[list["ApprovalAction"]] = relationship(back_populates="actor")
    submission_signings: Mapped[list["SubmissionSigning"]] = relationship(
        back_populates="signer", foreign_keys="SubmissionSigning.signer_id"
    )
    submission_attachments: Mapped[list["SubmissionAttachment"]] = relationship(back_populates="uploaded_by")

    __table_args__ = (Index("ix_users_status", "status"),)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[RoleCode] = mapped_column(
        SAEnum(RoleCode, name="RoleCode", native_enum=True), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    users: Mapped[list["UserRole"]] = relationship(back_populates="role")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        "role_id", PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = created_at_col()
    assigned_by: Mapped[uuid.UUID | None] = mapped_column("assigned_by", PGUUID(as_uuid=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship(back_populates="users")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column("token_hash", String, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column("expires_at", TIMESTAMPTZ, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column("revoked_at", TIMESTAMPTZ, nullable=True)
    user_agent: Mapped[str | None] = mapped_column("user_agent", String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column("ip_address", String, nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (Index("ix_refresh_tokens_user_id_revoked_at", "user_id", "revoked_at"),)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    student_code: Mapped[str] = mapped_column("student_code", String, unique=True, nullable=False)
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        "class_id", PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True
    )
    date_of_birth: Mapped[date | None] = mapped_column("date_of_birth", Date, nullable=True)
    place_of_birth: Mapped[str | None] = mapped_column("place_of_birth", String, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    enroll_year: Mapped[int | None] = mapped_column("enroll_year", Integer, nullable=True)
    cohort: Mapped[str | None] = mapped_column(String, nullable=True)
    training_system: Mapped[str | None] = mapped_column("training_system", String, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    user: Mapped["User"] = relationship(back_populates="student_profile")
    study_class: Mapped["StudyClass | None"] = relationship(back_populates="students")

    __table_args__ = (Index("ix_student_profiles_class_id", "class_id"),)


class ElectronicSignature(Base):
    __tablename__ = "electronic_signatures"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column("file_path", String, nullable=False)
    mime_type: Mapped[str] = mapped_column("mime_type", String, nullable=False)
    file_hash: Mapped[str] = mapped_column("file_hash", String, nullable=False)
    width_px: Mapped[int | None] = mapped_column("width_px", Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column("height_px", Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column("is_active", Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    user: Mapped["User"] = relationship(back_populates="signatures")
    signings: Mapped[list["SubmissionSigning"]] = relationship(back_populates="signature")

    __table_args__ = (Index("ix_electronic_signatures_user_id_is_active", "user_id", "is_active"),)


# NOTE: `StudyClass` (used above only as a string in `relationship("StudyClass | None", ...)`)
# lives in `app.models.academic`. No import is needed here — SQLAlchemy resolves
# relationship targets by class name through the shared `Base.registry` once all
# model modules have been imported (see `app/models/__init__.py`), avoiding a
# users.py <-> academic.py circular import.
