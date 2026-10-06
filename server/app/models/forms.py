from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import TIMESTAMPTZ, created_at_col, updated_at_col, uuid_pk
from app.models.enums import ApprovalActionType, RoleCode, StepStatus, SubmissionStatus


class FormTemplate(Base):
    __tablename__ = "form_templates"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    field_schema: Mapped[list] = mapped_column("field_schema", JSONB, nullable=False)
    template_path: Mapped[str] = mapped_column("template_path", String, nullable=False)
    approval_flow: Mapped[list] = mapped_column("approval_flow", JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column("is_active", Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    submissions: Mapped[list["FormSubmission"]] = relationship(back_populates="template")


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    template_id: Mapped[uuid.UUID] = mapped_column(
        "template_id", PGUUID(as_uuid=True), ForeignKey("form_templates.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        "owner_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, name="SubmissionStatus", native_enum=True), default=SubmissionStatus.DRAFT
    )
    form_data: Mapped[dict] = mapped_column("form_data", JSONB, nullable=False)
    profile_snapshot: Mapped[dict] = mapped_column("profile_snapshot", JSONB, nullable=False)
    generated_path: Mapped[str | None] = mapped_column("generated_path", String, nullable=True)
    generated_hash: Mapped[str | None] = mapped_column("generated_hash", String, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column("generated_at", TIMESTAMPTZ, nullable=True)
    signed_path: Mapped[str | None] = mapped_column("signed_path", String, nullable=True)
    signed_hash: Mapped[str | None] = mapped_column("signed_hash", String, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column("submitted_at", TIMESTAMPTZ, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column("completed_at", TIMESTAMPTZ, nullable=True)
    current_step_order: Mapped[int | None] = mapped_column("current_step_order", Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    template: Mapped["FormTemplate"] = relationship(back_populates="submissions")
    owner: Mapped["User"] = relationship(back_populates="submissions")
    steps: Mapped[list["ApprovalStep"]] = relationship(back_populates="submission", cascade="all, delete-orphan")
    actions: Mapped[list["ApprovalAction"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    signings: Mapped[list["SubmissionSigning"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )

    attachments: Mapped[list["SubmissionAttachment"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_form_submissions_owner_id_status", "owner_id", "status"),
        Index("ix_form_submissions_status_current_step_order", "status", "current_step_order"),
    )


class SubmissionAttachment(Base):
    """File đính kèm học viên tự tải lên cho một đơn (minh chứng, phụ lục...)
    — tách khỏi `generated_path`/`signed_path`: những cột đó là BẢN THÂN
    tờ đơn do hệ thống dựng, còn đây là tài liệu người dùng đưa thêm vào."""

    __tablename__ = "submission_attachments"

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        "submission_id",
        PGUUID(as_uuid=True),
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        "uploaded_by_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    file_path: Mapped[str] = mapped_column("file_path", String, nullable=False)
    file_name: Mapped[str] = mapped_column("file_name", String, nullable=False)
    mime_type: Mapped[str] = mapped_column("mime_type", String, nullable=False)
    size_bytes: Mapped[int] = mapped_column("size_bytes", Integer, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    submission: Mapped["FormSubmission"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User"] = relationship(back_populates="submission_attachments")

    __table_args__ = (Index("ix_submission_attachments_submission_id", "submission_id"),)


class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        "submission_id",
        PGUUID(as_uuid=True),
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column("step_order", Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    role_code: Mapped[RoleCode] = mapped_column(
        "role_code", SAEnum(RoleCode, name="RoleCode", native_enum=True), nullable=False
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        "assignee_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[StepStatus] = mapped_column(
        SAEnum(StepStatus, name="StepStatus", native_enum=True), default=StepStatus.PENDING
    )
    decided_at: Mapped[datetime | None] = mapped_column("decided_at", TIMESTAMPTZ, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission: Mapped["FormSubmission"] = relationship(back_populates="steps")
    assignee: Mapped["User | None"] = relationship(back_populates="approval_steps")

    __table_args__ = (
        UniqueConstraint("submission_id", "step_order", name="uq_approval_steps_submission_step_order"),
        Index("ix_approval_steps_assignee_id_status", "assignee_id", "status"),
    )


class ApprovalAction(Base):
    """Insert-only: only ever INSERT from the service layer, never UPDATE/DELETE."""

    __tablename__ = "approval_actions"

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        "submission_id",
        PGUUID(as_uuid=True),
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        "actor_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[ApprovalActionType] = mapped_column(
        SAEnum(ApprovalActionType, name="ApprovalActionType", native_enum=True), nullable=False
    )
    step_order: Mapped[int | None] = mapped_column("step_order", Integer, nullable=True)
    from_status: Mapped[SubmissionStatus | None] = mapped_column(
        "from_status", SAEnum(SubmissionStatus, name="SubmissionStatus", native_enum=True), nullable=True
    )
    to_status: Mapped[SubmissionStatus] = mapped_column(
        "to_status", SAEnum(SubmissionStatus, name="SubmissionStatus", native_enum=True), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column("ip_address", String, nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    submission: Mapped["FormSubmission"] = relationship(back_populates="actions")
    actor: Mapped["User"] = relationship(back_populates="approval_actions")

    __table_args__ = (Index("ix_approval_actions_submission_id_created_at", "submission_id", "created_at"),)


class SubmissionSigning(Base):
    __tablename__ = "submission_signings"

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        "submission_id",
        PGUUID(as_uuid=True),
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    signer_id: Mapped[uuid.UUID] = mapped_column(
        "signer_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    signature_id: Mapped[uuid.UUID | None] = mapped_column(
        "signature_id",
        PGUUID(as_uuid=True),
        ForeignKey("electronic_signatures.id", ondelete="SET NULL"),
        nullable=True,
    )
    hash_before: Mapped[str] = mapped_column("hash_before", String, nullable=False)
    hash_after: Mapped[str] = mapped_column("hash_after", String, nullable=False)
    step_order: Mapped[int | None] = mapped_column("step_order", Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column("ip_address", String, nullable=True)
    session_id: Mapped[str | None] = mapped_column("session_id", String, nullable=True)
    signed_at: Mapped[datetime] = created_at_col()

    submission: Mapped["FormSubmission"] = relationship(back_populates="signings")
    signature: Mapped["ElectronicSignature | None"] = relationship(back_populates="signings")
    signer: Mapped["User"] = relationship(back_populates="submission_signings", foreign_keys=[signer_id])

    __table_args__ = (
        Index("ix_submission_signings_submission_id_signed_at", "submission_id", "signed_at"),
        Index("ix_submission_signings_signer_id_signed_at", "signer_id", "signed_at"),
    )
