"""Forms: templates, submissions, autofill, validation, DOCX render, e-sign,
submit. Port of the (deleted) NestJS `forms.service.ts`. This is the largest
and most security-sensitive service in the port — every rule called out in
the porting notes is preserved:

- Autofill is resolved through an explicit whitelist (`_SOURCES`), never by
  walking arbitrary attribute paths — a tampered `field_schema` can't be
  used to read something like `user.password_hash`.
- The 7 identity fields (fullName, dateOfBirth, className, cohort,
  studentCode, phone, trainingSystem) are a fixed universal autofill set,
  resolved from the caller's OWN profile every time — never declared in a
  template's `field_schema.fields[]`, and never taken from client input.
- `validate_against_schema` silently drops unknown/unschematized keys
  rather than erroring on them (erroring would itself leak which field
  names the server cares about).
- Table fields: rows are filtered down to the declared columns, empty rows
  dropped, `maxRows` enforced (default 20).
- Two cross-field rules that are template-specific, not schema-driven: the
  leave date range check, and the 1-3-day vs >3-day cutoff (checked by
  `template_code`, since both leave templates share the same field names).
- `is_editable = status in {DRAFT, NEEDS_REVISION} and not signed_hash` —
  once signed, even a DRAFT submission is locked.
- Every submission load is by-owner: 404 (not 403) if the caller isn't the
  owner — anti-enumeration, matches the documents/chat pattern already in
  this codebase.
- File writes happen BEFORE the DB transaction commits, same latent
  ordering as the reference — preserved deliberately, not "fixed".
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.enums import SubmissionStatus
from app.models.forms import (
    FormSubmission,
    FormTemplate,
)
from app.models.users import StudentProfile, User
from app.schemas.forms import CreateSubmissionDto, UpdateSubmissionDto
from app.services.accounts.audit_service import AuditService
from app.services.forms.signatures_service import SignaturesService
from app.services.documents.storage_service import StorageService

from app.services.forms.forms_common import (
    EDITABLE_STATUSES,
    _SOURCES,
    _is_uuid,
)
from app.services.forms.forms_files import FilesMixin
from app.services.forms.forms_signing import SigningMixin
from app.services.forms.forms_stats import StatsMixin
from app.services.forms.forms_validation import ValidationMixin


class FormsService(ValidationMixin, FilesMixin, SigningMixin, StatsMixin):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = StorageService()
        self.audit = AuditService(db)
        self.signatures = SignaturesService(db)

    # ------------------------------------------------------------ autofill

    async def _load_profile(self, user_id: str) -> tuple[User, StudentProfile | None]:
        stmt = (
            select(User)
            .options(selectinload(User.student_profile).selectinload(StudentProfile.study_class))
            .where(User.id == user_id)
        )
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})
        return user, user.student_profile

    async def _resolve_identity(self, user_id: str) -> tuple[dict, list[str]]:
        user, profile = await self._load_profile(user_id)
        snapshot: dict = {}
        missing: list[str] = []
        for key, resolver in _SOURCES.items():
            value = resolver(user, profile)
            if value:
                snapshot[key] = value
            else:
                missing.append(key)
        return snapshot, missing

    # ------------------------------------------------------------ templates

    async def list_templates(self) -> dict:
        stmt = select(FormTemplate).order_by(FormTemplate.is_active.desc(), FormTemplate.name.asc())
        rows = (await self.db.execute(stmt)).scalars().all()
        return {"items": [self._present_template_summary(t) for t in rows]}

    async def get_template(self, code: str, user: AuthenticatedUser) -> dict:
        template = (
            await self.db.execute(select(FormTemplate).where(FormTemplate.code == code))
        ).scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy mẫu đơn"})

        snapshot, missing = await self._resolve_identity(user.id)
        return {
            "id": str(template.id),
            "code": template.code,
            "name": template.name,
            "description": template.description,
            "fields": template.field_schema,
            "approvalFlow": template.approval_flow,
            "isActive": template.is_active,
            "autofill": snapshot,
            "missingProfileFields": missing,
        }

    @staticmethod
    def _present_template_summary(t: FormTemplate) -> dict:
        return {
            "id": str(t.id),
            "code": t.code,
            "name": t.name,
            "description": t.description,
            "isActive": t.is_active,
        }

    # ---------------------------------------------------------- code gen

    async def _next_code(self, template_code: str) -> str:
        prefix = "NH" if template_code.startswith("DON_XIN_NGHI_HOC") else "DON"
        year = datetime.now(timezone.utc).year
        like_pattern = f"{prefix}-{year}-%"
        count = (
            await self.db.execute(
                select(func.count()).select_from(FormSubmission).where(FormSubmission.code.like(like_pattern))
            )
        ).scalar_one()
        return f"{prefix}-{year}-{count + 1:04d}"

    # ------------------------------------------------------------- CRUD

    async def create(self, dto: CreateSubmissionDto, user: AuthenticatedUser, request: Request | None) -> dict:
        template = (
            await self.db.execute(
                select(FormTemplate).where(FormTemplate.code == dto.template_code, FormTemplate.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy mẫu đơn"})

        snapshot, missing = await self._resolve_identity(user.id)
        if missing:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Hồ sơ của bạn còn thiếu thông tin bắt buộc để tạo đơn: " + ", ".join(missing),
                    "code": "MISSING_PROFILE_DATA",
                    "missingFields": missing,
                },
            )

        cleaned = self._validate_against_schema(template.code, template.field_schema, dto.form_data)
        code = await self._next_code(template.code)

        submission = FormSubmission(
            template_id=template.id,
            owner_id=user.id,
            code=code,
            status=SubmissionStatus.DRAFT,
            form_data=cleaned,
            profile_snapshot=snapshot,
        )
        self.db.add(submission)
        await self.db.flush()

        await self.audit.log(
            action="FORM_CREATE", user_id=user.id, entity_type="FormSubmission", entity_id=str(submission.id),
            detail={"templateCode": template.code, "code": code}, request=request,
        )
        await self.db.commit()
        return await self.get(str(submission.id), user)

    async def _load_owned(self, id: str, user_id: str) -> tuple[FormSubmission, FormTemplate]:
        if not _is_uuid(id):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy đơn"})
        stmt = (
            select(FormSubmission)
            .options(selectinload(FormSubmission.template), selectinload(FormSubmission.attachments))
            .where(FormSubmission.id == id)
        )
        submission = (await self.db.execute(stmt)).scalar_one_or_none()
        if not submission or str(submission.owner_id) != str(user_id):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy đơn"})
        return submission, submission.template

    async def get(self, id: str, user: AuthenticatedUser) -> dict:
        submission, template = await self._load_owned(id, user.id)
        return self._present_detail(submission, template)

    async def list(self, user: AuthenticatedUser, *, status_: SubmissionStatus | None, page: int, page_size: int) -> dict:
        conditions = [FormSubmission.owner_id == user.id]
        if status_ is not None:
            conditions.append(FormSubmission.status == status_)

        count_stmt = select(func.count()).select_from(FormSubmission)
        stmt = select(FormSubmission).options(selectinload(FormSubmission.template))
        for c in conditions:
            count_stmt = count_stmt.where(c)
            stmt = stmt.where(c)

        total = (await self.db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(FormSubmission.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()

        return {
            "total": total, "page": page, "pageSize": page_size,
            "items": [self._present_summary(s, s.template) for s in rows],
        }

    async def update(self, id: str, dto: UpdateSubmissionDto, user: AuthenticatedUser, request: Request | None) -> dict:
        submission, template = await self._load_owned(id, user.id)
        if submission.signed_hash or submission.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail={"message": "Đơn đã ký hoặc không ở trạng thái có thể chỉnh sửa", "code": "NOT_EDITABLE"},
            )

        cleaned = self._validate_against_schema(template.code, template.field_schema, dto.form_data)
        submission.form_data = cleaned
        # Content changed -> any previously rendered file is stale.
        submission.generated_path = None
        submission.generated_hash = None
        submission.generated_at = None
        await self.db.flush()

        await self.audit.log(
            action="FORM_UPDATE", user_id=user.id, entity_type="FormSubmission", entity_id=str(submission.id),
            request=request,
        )
        await self.db.commit()
        return await self.get(id, user)

    async def remove(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        submission, _ = await self._load_owned(id, user.id)
        if submission.status != SubmissionStatus.DRAFT or submission.signed_hash:
            raise HTTPException(
                status_code=400,
                detail={"message": "Chỉ có thể xóa đơn nháp chưa ký", "code": "NOT_DELETABLE"},
            )
        code = submission.code
        await self.db.delete(submission)
        await self.audit.log(
            action="FORM_DELETE", user_id=user.id, entity_type="FormSubmission", entity_id=str(id),
            detail={"code": code}, request=request,
        )
        await self.db.commit()
        return {"message": f'Đã xóa đơn "{code}"'}

    # ----------------------------------------------------------- present

    @staticmethod
    def _status_label(status: SubmissionStatus) -> str:
        return {
            SubmissionStatus.DRAFT: "Bản nháp",
            SubmissionStatus.SUBMITTED: "Đã gửi trình ký",
            SubmissionStatus.UNDER_REVIEW: "Đang duyệt",
            SubmissionStatus.NEEDS_REVISION: "Yêu cầu bổ sung",
            SubmissionStatus.REJECTED: "Không được duyệt",
            SubmissionStatus.APPROVED: "Đã duyệt",
            SubmissionStatus.COMPLETED: "Đã hoàn thành",
        }[status]

    @classmethod
    def _present_summary(cls, s: FormSubmission, t: FormTemplate) -> dict:
        return {
            "id": str(s.id),
            "code": s.code,
            "status": s.status,
            "statusLabel": cls._status_label(s.status),
            "createdAt": s.created_at,
            "submittedAt": s.submitted_at,
            "generatedAt": s.generated_at,
            "signed": bool(s.signed_hash),
            "currentStepOrder": s.current_step_order,
            "template": {"code": t.code, "name": t.name},
        }

    @classmethod
    def _present_detail(cls, s: FormSubmission, t: FormTemplate) -> dict:
        is_editable = s.status in EDITABLE_STATUSES and not s.signed_hash
        return {
            "id": str(s.id),
            "code": s.code,
            "status": s.status,
            "statusLabel": cls._status_label(s.status),
            "editable": is_editable,
            "formData": s.form_data,
            "profileSnapshot": s.profile_snapshot,
            "generatedAt": s.generated_at,
            "generatedHash": s.generated_hash,
            "signedHash": s.signed_hash,
            "submittedAt": s.submitted_at,
            "completedAt": s.completed_at,
            "currentStepOrder": s.current_step_order,
            "createdAt": s.created_at,
            "attachments": [
                {
                    "id": str(a.id),
                    "fileName": a.file_name,
                    "mimeType": a.mime_type,
                    "sizeBytes": a.size_bytes,
                    "createdAt": a.created_at,
                }
                for a in sorted(s.attachments, key=lambda a: a.created_at)
            ],
            "template": {
                "code": t.code,
                "name": t.name,
                "fields": t.field_schema,
                "approvalFlow": t.approval_flow,
            },
        }
