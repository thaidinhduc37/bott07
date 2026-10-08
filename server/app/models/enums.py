"""Các enum dùng chung cho model, lưu dưới dạng enum gốc của Postgres qua `Enum(..., name=...)`."""

from __future__ import annotations

import enum


class RoleCode(str, enum.Enum):
    ADMIN = "ADMIN"
    ACADEMIC_MANAGER = "ACADEMIC_MANAGER"
    LECTURER = "LECTURER"
    APPROVER = "APPROVER"
    STUDENT = "STUDENT"
    DEPARTMENT_HEAD = "DEPARTMENT_HEAD"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class SessionType(str, enum.Enum):
    LY_THUYET = "LY_THUYET"
    THUC_HANH = "THUC_HANH"
    KIEM_TRA_GIUA_KY = "KIEM_TRA_GIUA_KY"
    ON_TAP = "ON_TAP"
    HOC_BU = "HOC_BU"


class ScheduleStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    HOLIDAY = "HOLIDAY"
    COMPLETED = "COMPLETED"


class ExamFormat(str, enum.Enum):
    TRAC_NGHIEM = "TRAC_NGHIEM"
    TU_LUAN = "TU_LUAN"
    THUC_HANH = "THUC_HANH"
    KET_HOP = "KET_HOP"


class ExamStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"


class DocumentType(str, enum.Enum):
    QUYCHE = "QUYCHE"
    GIAOTRINH = "GIAOTRINH"
    KHAC = "KHAC"


class IndexStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class ChatMode(str, enum.Enum):
    QUYCHE = "QUYCHE"
    GIAOTRINH = "GIAOTRINH"


class MessageRole(str, enum.Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class NotificationType(str, enum.Enum):
    SUBMISSION_STATUS = "SUBMISSION_STATUS"
    SCHEDULE_CHANGE = "SCHEDULE_CHANGE"
    DOCUMENT_INDEXED = "DOCUMENT_INDEXED"
    SYSTEM = "SYSTEM"


class SubmissionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    NEEDS_REVISION = "NEEDS_REVISION"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"


class StepStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    SKIPPED = "SKIPPED"


class ApprovalActionType(str, enum.Enum):
    SUBMIT = "SUBMIT"
    RECEIVE = "RECEIVE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"
    RESUBMIT = "RESUBMIT"
    SIGN = "SIGN"
    COMPLETE = "COMPLETE"
