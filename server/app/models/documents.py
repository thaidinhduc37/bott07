from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TIMESTAMPTZ, created_at_col, updated_at_col, uuid_pk
from app.models.enums import DocumentType, IndexStatus


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String, nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        "document_type", SAEnum(DocumentType, name="DocumentType", native_enum=True), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        "course_id", PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    reference_no: Mapped[str | None] = mapped_column("reference_no", String, nullable=True)
    issued_at: Mapped[date | None] = mapped_column("issued_at", Date, nullable=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        "uploaded_by_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    course: Mapped["Course | None"] = relationship(back_populates="documents")
    uploaded_by: Mapped["User"] = relationship(back_populates="uploaded_documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_documents_document_type_course_id", "document_type", "course_id"),)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        "document_id", PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column("file_path", String, nullable=False)
    file_name: Mapped[str] = mapped_column("file_name", String, nullable=False)
    mime_type: Mapped[str] = mapped_column("mime_type", String, nullable=False)
    file_size: Mapped[int] = mapped_column("file_size", Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column("file_hash", String, nullable=False)
    index_status: Mapped[IndexStatus] = mapped_column(
        "index_status", SAEnum(IndexStatus, name="IndexStatus", native_enum=True), default=IndexStatus.UPLOADED
    )
    index_error: Mapped[str | None] = mapped_column("index_error", String, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column("indexed_at", TIMESTAMPTZ, nullable=True)
    page_count: Mapped[int | None] = mapped_column("page_count", Integer, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column("chunk_count", Integer, nullable=True)
    contextual_count: Mapped[int | None] = mapped_column("contextual_count", Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    document: Mapped["Document"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_versions_doc_version"),
        Index("ix_document_versions_index_status", "index_status"),
    )
