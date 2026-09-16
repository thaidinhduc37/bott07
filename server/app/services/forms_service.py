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

import hashlib
import re
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.deps import AuthenticatedUser
from app.models.enums import ApprovalActionType, NotificationType, RoleCode, StepStatus, SubmissionStatus
from app.models.forms import (
    ApprovalAction,
    ApprovalStep,
    FormSubmission,
    FormTemplate,
    SubmissionAttachment,
    SubmissionSigning,
)
from app.models.notifications import Notification
from app.models.users import Role, StudentProfile, User, UserRole
from app.schemas.forms import CreateSubmissionDto, UpdateSubmissionDto
from app.security import ACCESS_COOKIE, hash_token
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.docx_renderer import OWNER_SIGNATURE_TITLE, SignatureSlot, render_form
from app.services.form_layouts import layout_for
from app.services.signatures_service import SignaturesService
from app.services.storage_service import StorageError, StorageService

EDITABLE_STATUSES = {SubmissionStatus.DRAFT, SubmissionStatus.NEEDS_REVISION}

# The universal 7-field autofill set. Every value is resolved from the
# CALLER's own User/StudentProfile/StudyClass rows — never from client input,
# never from another user's data (no id/user param taken from the request).
_SOURCES = {
    "fullName": lambda u, p: u.full_name,
    "dateOfBirth": lambda u, p: p.date_of_birth.isoformat() if p and p.date_of_birth else None,
    "className": lambda u, p: p.study_class.code if p and p.study_class else None,
    "cohort": lambda u, p: p.cohort if p else None,
    "studentCode": lambda u, p: p.student_code if p else None,
    "phone": lambda u, p: u.phone,
    "trainingSystem": lambda u, p: p.training_system if p else None,
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _convert_iso_dates(data: dict) -> dict:
    out: dict = {}
    for k, v in data.items():
        if isinstance(v, str) and _ISO_DATE_RE.match(v):
            y, m, d = v.split("-")
            out[k] = f"{d}/{m}/{y}"
        else:
            out[k] = v
    return out


def _extract_raw_token(request: Request | None) -> str | None:
    if request is None:
        return None
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        return token
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:]
    return None


class FormsService:
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

    # ----------------------------------------------------------- validation

    def _validate_against_schema(self, template_code: str, field_schema: list, form_data: dict) -> dict:
        out: dict = {}
        for f in field_schema:
            key = f["key"]
            ftype = f.get("type", "text")
            required = bool(f.get("required"))
            label = f.get("label", key)

            if ftype == "table":
                raw_rows = form_data.get(key)
                raw_rows = raw_rows if isinstance(raw_rows, list) else []
                declared_cols = {c["key"] for c in f.get("columns", [])}
                max_rows = f.get("maxRows", 20)
                cleaned_rows = []
                for row in raw_rows:
                    if not isinstance(row, dict):
                        continue
                    filtered = {k: v for k, v in row.items() if k in declared_cols}
                    if not any(str(v).strip() for v in filtered.values() if v not in (None, "")):
                        continue  # drop empty rows
                    cleaned_rows.append(filtered)
                cleaned_rows = cleaned_rows[:max_rows]
                if required and not cleaned_rows:
                    raise HTTPException(
                        status_code=400,
                        detail={"message": f'Trường "{label}" là bắt buộc', "code": "VALIDATION_ERROR"},
                    )
                out[key] = cleaned_rows
                continue

            value = form_data.get(key)
            if isinstance(value, str):
                value = value.strip()
            if required and (value is None or value == ""):
                raise HTTPException(
                    status_code=400, detail={"message": f'Trường "{label}" là bắt buộc', "code": "VALIDATION_ERROR"}
                )
            max_length = f.get("maxLength")
            if isinstance(value, str) and max_length and len(value) > max_length:
                raise HTTPException(
                    status_code=400,
                    detail={"message": f'Trường "{label}" vượt quá độ dài cho phép', "code": "VALIDATION_ERROR"},
                )
            if value not in (None, ""):
                out[key] = value
        # Unknown keys in form_data that aren't declared anywhere above are
        # simply never copied into `out` — silent drop, not an error.

        self._validate_cross_field_rules(template_code, out)
        return out

    @staticmethod
    def _validate_cross_field_rules(template_code: str, data: dict) -> None:
        leave_from = data.get("leaveFrom")
        leave_to = data.get("leaveTo")
        if not (isinstance(leave_from, str) and isinstance(leave_to, str)):
            return
        try:
            d_from = date.fromisoformat(leave_from[:10])
            d_to = date.fromisoformat(leave_to[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Ngày nghỉ học không hợp lệ", "code": "VALIDATION_ERROR"})

        if d_to < d_from:
            raise HTTPException(
                status_code=400,
                detail={"message": "Ngày kết thúc nghỉ học phải sau ngày bắt đầu", "code": "INVALID_DATE_RANGE"},
            )

        days = (d_to - d_from).days + 1
        if template_code == "DON_XIN_NGHI_HOC" and days > 3:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": (
                        "Đơn xin phép nghỉ học (1-3 ngày) chỉ áp dụng cho tối đa 3 ngày. "
                        "Vui lòng dùng mẫu Đơn xin nghỉ học (trên 3 ngày)."
                    ),
                    "code": "LEAVE_RANGE_TOO_LONG",
                },
            )
        if template_code == "DON_XIN_NGHI_HOC_TREN_3" and days <= 3:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": (
                        "Đơn xin nghỉ học (trên 3 ngày) chỉ áp dụng khi nghỉ trên 3 ngày. "
                        "Vui lòng dùng mẫu Đơn xin phép nghỉ học (1-3 ngày)."
                    ),
                    "code": "LEAVE_RANGE_TOO_SHORT",
                },
            )

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

    # ------------------------------------------------------------ attachments

    _ATTACHMENT_ACCEPT = [".pdf", ".png", ".jpg", ".jpeg", ".docx"]
    _ATTACHMENT_MAX_COUNT = 10

    async def add_attachment(
        self, id: str, user: AuthenticatedUser, *, file_bytes: bytes, original_filename: str,
    ) -> dict:
        submission, _ = await self._load_owned(id, user.id)
        if len(submission.attachments) >= self._ATTACHMENT_MAX_COUNT:
            raise HTTPException(
                status_code=400,
                detail={"message": f"Mỗi đơn chỉ đính kèm tối đa {self._ATTACHMENT_MAX_COUNT} file", "code": "TOO_MANY_ATTACHMENTS"},
            )
        try:
            stored = self.storage.save(
                data=file_bytes, original_filename=original_filename,
                subdir="attachments", accept=self._ATTACHMENT_ACCEPT,
            )
        except StorageError as e:
            raise HTTPException(status_code=400, detail={"message": e.message, "code": e.code})

        attachment = SubmissionAttachment(
            submission_id=submission.id, uploaded_by_id=user.id,
            file_path=stored.relative_path, file_name=stored.file_name,
            mime_type=stored.mime_type, size_bytes=stored.size,
        )
        self.db.add(attachment)
        await self.audit.log(
            action="FORM_ATTACHMENT_ADD", user_id=user.id, entity_type="FormSubmission", entity_id=str(id),
            detail={"fileName": stored.file_name}, request=None,
        )
        await self.db.commit()
        return await self.get(id, user)

    async def remove_attachment(self, id: str, attachment_id: str, user: AuthenticatedUser) -> dict:
        submission, _ = await self._load_owned(id, user.id)
        attachment = next((a for a in submission.attachments if str(a.id) == attachment_id), None)
        if not attachment:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy file đính kèm"})

        self.storage.remove(attachment.file_path)
        await self.db.delete(attachment)
        await self.audit.log(
            action="FORM_ATTACHMENT_REMOVE", user_id=user.id, entity_type="FormSubmission", entity_id=str(id),
            detail={"fileName": attachment.file_name}, request=None,
        )
        await self.db.commit()
        return await self.get(id, user)

    async def get_attachment_file(self, id: str, attachment_id: str, user: AuthenticatedUser) -> tuple[bytes, str, str]:
        """Trả về (bytes, file_name, mime_type). Chủ đơn xem được file đính kèm
        của chính đơn mình, bất kể đơn đang ở trạng thái nào — không có lý do
        hạn chế đọc lại thứ chính mình đã tải lên."""
        submission, _ = await self._load_owned(id, user.id)
        attachment = next((a for a in submission.attachments if str(a.id) == attachment_id), None)
        if not attachment:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy file đính kèm"})
        data = self.storage.absolute(attachment.file_path).read_bytes()
        return data, attachment.file_name, attachment.mime_type

    # ---------------------------------------------------------------- docx

    def build_docx(self, submission: FormSubmission, template: FormTemplate, signatures: dict[str, dict]) -> bytes:
        layout = layout_for(template.code)
        merged = {**submission.profile_snapshot, **submission.form_data}
        merged = _convert_iso_dates(merged)

        flow = sorted(template.approval_flow, key=lambda s: s["order"], reverse=True)
        slots: list[SignatureSlot] = []
        for step in flow:
            info = signatures.get(str(step["order"]))
            if info:
                slots.append(SignatureSlot(
                    title=step["title"], signed=True, image_bytes=info["image_bytes"],
                    signed_by=info["signed_by"], signed_at=info["signed_at"],
                ))
            else:
                slots.append(SignatureSlot(title=step["title"]))

        owner_info = signatures.get("owner")
        if owner_info:
            slots.append(SignatureSlot(
                title=OWNER_SIGNATURE_TITLE, signed=True, image_bytes=owner_info["image_bytes"],
                signed_by=owner_info["signed_by"], signed_at=owner_info["signed_at"],
            ))
        else:
            slots.append(SignatureSlot(title=OWNER_SIGNATURE_TITLE))

        return render_form(layout, merged, slots)

    def _write_generated(self, filename: str, data: bytes) -> tuple[str, str]:
        return self.storage.write_named("generated-forms", filename, data)

    async def render(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        submission, template = await self._load_owned(id, user.id)
        data = self.build_docx(submission, template, signatures={})
        relative_path, file_hash = self._write_generated(f"{submission.code}.docx", data)

        submission.generated_path = relative_path
        submission.generated_hash = file_hash
        submission.generated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.audit.log(
            action="FORM_RENDER", user_id=user.id, entity_type="FormSubmission", entity_id=str(submission.id),
            request=request,
        )
        await self.db.commit()
        return {
            "code": submission.code, "hash": file_hash, "bytes": len(data),
            "generatedAt": submission.generated_at,
        }

    # -------------------------------------------------------------- sign

    async def sign(self, id: str, pin: str, user: AuthenticatedUser, request: Request | None) -> dict:
        submission, template = await self._load_owned(id, user.id)

        if submission.signed_hash:
            raise HTTPException(status_code=400, detail={"message": "Đơn đã được ký", "code": "ALREADY_SIGNED"})
        if submission.status not in EDITABLE_STATUSES:
            raise HTTPException(status_code=400, detail={"message": "Đơn không ở trạng thái có thể ký", "code": "NOT_EDITABLE"})

        active_sig = await self.signatures.get_active_for_user(user.id)
        if not active_sig:
            raise HTTPException(
                status_code=400,
                detail={"message": "Bạn chưa đăng ký chữ ký điện tử", "code": "NO_SIGNATURE"},
            )

        auth = AuthService(self.db)
        pin_ok = await auth.verify_signature_pin(user.id, pin)
        if not pin_ok:
            await self.audit.log(
                action="FORM_SIGN_FAILED", user_id=user.id, entity_type="FormSubmission", entity_id=str(submission.id),
                request=request,
            )
            await self.db.commit()
            raise HTTPException(status_code=401, detail={"message": "Mã PIN không đúng", "code": "BAD_PIN"})

        # File writes happen BEFORE the DB transaction commits — same
        # ordering as the reference; preserved as-is, not "fixed".
        unsigned_bytes = self.build_docx(submission, template, signatures={})
        unsigned_path, hash_before = self._write_generated(f"{submission.code}.docx", unsigned_bytes)

        image_bytes = self.signatures.read_image_bytes(active_sig)
        signed_at = datetime.now(timezone.utc)
        signed_bytes = self.build_docx(
            submission, template,
            signatures={"owner": {"image_bytes": image_bytes, "signed_by": user.full_name, "signed_at": signed_at}},
        )
        signed_path, hash_after = self._write_generated(f"{submission.code}-signed.docx", signed_bytes)

        submission.generated_path = unsigned_path
        submission.generated_hash = hash_before
        submission.generated_at = signed_at
        submission.signed_path = signed_path
        submission.signed_hash = hash_after
        await self.db.flush()

        raw_token = _extract_raw_token(request)
        self.db.add(SubmissionSigning(
            submission_id=submission.id, signer_id=user.id, signature_id=active_sig.id,
            hash_before=hash_before, hash_after=hash_after, step_order=None,
            ip_address=request.client.host if request and request.client else None,
            session_id=hash_token(raw_token)[:16] if raw_token else None,
        ))
        await self.audit.log(
            action="FORM_SIGN", user_id=user.id, entity_type="FormSubmission", entity_id=str(submission.id),
            request=request,
        )
        await self.db.commit()
        return await self.get(id, user)

    # ------------------------------------------------------------- submit

    async def submit(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        submission, template = await self._load_owned(id, user.id)

        if not submission.signed_hash:
            raise HTTPException(status_code=400, detail={"message": "Đơn phải được ký trước khi nộp", "code": "NOT_SIGNED"})
        if submission.status not in EDITABLE_STATUSES:
            raise HTTPException(status_code=400, detail={"message": "Đơn không ở trạng thái có thể nộp", "code": "NOT_EDITABLE"})
        if not template.approval_flow:
            raise HTTPException(status_code=400, detail={"message": "Mẫu đơn chưa cấu hình quy trình duyệt", "code": "NO_APPROVAL_FLOW"})

        is_resubmit = submission.status == SubmissionStatus.NEEDS_REVISION
        from_status = submission.status
        flow = sorted(template.approval_flow, key=lambda s: s["order"])

        existing_stmt = select(ApprovalStep).where(ApprovalStep.submission_id == submission.id)
        existing_by_order = {s.step_order: s for s in (await self.db.execute(existing_stmt)).scalars().all()}

        for step in flow:
            row = existing_by_order.get(step["order"])
            if row is None:
                row = ApprovalStep(
                    submission_id=submission.id, step_order=step["order"], title=step["title"],
                    role_code=RoleCode(step["roleCode"]),
                )
                self.db.add(row)
            else:
                row.title = step["title"]
                row.role_code = RoleCode(step["roleCode"])
            # Resubmit resets ALL steps to PENDING — an approver who already
            # requested revision must see the resubmission fresh.
            row.status = StepStatus.PENDING
            row.decided_at = None
            row.comment = None

        first_order = flow[0]["order"]
        submission.status = SubmissionStatus.SUBMITTED
        submission.current_step_order = first_order
        submission.submitted_at = datetime.now(timezone.utc)
        await self.db.flush()

        self.db.add(ApprovalAction(
            submission_id=submission.id, actor_id=user.id,
            action=ApprovalActionType.RESUBMIT if is_resubmit else ApprovalActionType.SUBMIT,
            step_order=None, from_status=from_status, to_status=SubmissionStatus.SUBMITTED,
            ip_address=request.client.host if request and request.client else None,
        ))

        first_role = flow[0]["roleCode"]
        role_users_stmt = (
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == RoleCode(first_role))
        )
        recipient_ids = [r[0] for r in (await self.db.execute(role_users_stmt)).all()]
        for recipient_id in recipient_ids:
            self.db.add(Notification(
                user_id=recipient_id, type=NotificationType.SUBMISSION_STATUS,
                title=f"{submission.code}: Đơn chờ tiếp nhận",
                body=f'Đơn "{template.name}" ({submission.code}) đang chờ bạn tiếp nhận xử lý.',
                link_to=f"/phe-duyet/{submission.id}",
            ))

        await self.audit.log(
            action="FORM_RESUBMIT" if is_resubmit else "FORM_SUBMIT", user_id=user.id,
            entity_type="FormSubmission", entity_id=str(submission.id), request=request,
        )
        await self.db.commit()
        return await self.get(id, user)

    # ------------------------------------------------------------- verify

    async def verify(self, id: str, user: AuthenticatedUser) -> dict:
        submission, template = await self._load_owned(id, user.id)

        path = submission.signed_path or submission.generated_path
        expected = submission.signed_hash or submission.generated_hash
        if not path or not expected:
            return {"verified": None, "message": "Đơn chưa được tạo file", "signings": []}

        abs_path = self.storage.absolute(path)
        try:
            actual = hashlib.sha256(abs_path.read_bytes()).hexdigest()
        except FileNotFoundError:
            return {"verified": False, "message": "Không tìm thấy file trên đĩa", "signings": []}

        signings_stmt = (
            select(SubmissionSigning)
            .options(selectinload(SubmissionSigning.signer))
            .where(SubmissionSigning.submission_id == submission.id)
            .order_by(SubmissionSigning.signed_at.asc())
        )
        signings = (await self.db.execute(signings_stmt)).scalars().all()

        return {
            "verified": actual == expected,
            "message": "Khớp với dữ liệu đã ký" if actual == expected else "File đã bị thay đổi sau khi ký",
            "signings": [
                {
                    "signerId": str(s.signer_id), "signerName": s.signer.full_name if s.signer else None,
                    "stepOrder": s.step_order, "hashBefore": s.hash_before, "hashAfter": s.hash_after,
                    "signedAt": s.signed_at,
                }
                for s in signings
            ],
        }

    # ------------------------------------------------------------ file_of

    async def file_of(self, id: str, user: AuthenticatedUser, variant: str | None) -> tuple[str, str]:
        submission, _ = await self._load_owned(id, user.id)
        want_unsigned = variant == "chua-ky"
        path = submission.generated_path if want_unsigned else (submission.signed_path or submission.generated_path)
        if not path:
            raise HTTPException(status_code=404, detail={"message": "Đơn chưa có file"})
        abs_path = self.storage.absolute(path)
        if not abs_path.exists():
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy file trên đĩa"})
        suffix = "-da-ky" if not want_unsigned and submission.signed_path else ""
        filename = f"{submission.code}{suffix}.docx"
        return str(abs_path), filename

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

    # ------------------------------------------------------- admin stats

    async def get_admin_stats(self) -> dict:
        by_status_rows = (
            await self.db.execute(select(FormSubmission.status, func.count()).group_by(FormSubmission.status))
        ).all()
        by_template_rows = (
            await self.db.execute(
                select(FormTemplate.code, func.count())
                .join(FormSubmission, FormSubmission.template_id == FormTemplate.id)
                .group_by(FormTemplate.code)
            )
        ).all()

        completed_stmt = select(FormSubmission.submitted_at, FormSubmission.completed_at).where(
            FormSubmission.status == SubmissionStatus.COMPLETED,
            FormSubmission.completed_at.is_not(None),
            FormSubmission.submitted_at.is_not(None),
        )
        completed_rows = (await self.db.execute(completed_stmt)).all()
        if completed_rows:
            total_hours = sum((c - s).total_seconds() / 3600 for s, c in completed_rows)
            avg_turnaround = total_hours / len(completed_rows)
        else:
            avg_turnaround = None

        backlog_stmt = (
            select(FormSubmission)
            .options(selectinload(FormSubmission.template))
            .where(FormSubmission.status.in_([
                SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW, SubmissionStatus.NEEDS_REVISION,
            ]))
            .order_by(FormSubmission.submitted_at.asc())
            .limit(10)
        )
        backlog_rows = (await self.db.execute(backlog_stmt)).scalars().all()

        thirty_days_ago = datetime.now(timezone.utc).timestamp() - 30 * 86400
        recent_stmt = select(FormSubmission.status).where(
            FormSubmission.updated_at >= datetime.fromtimestamp(thirty_days_ago, tz=timezone.utc)
        )
        recent_statuses = [r[0] for r in (await self.db.execute(recent_stmt)).all()]
        decided = [s for s in recent_statuses if s in (SubmissionStatus.REJECTED, SubmissionStatus.APPROVED, SubmissionStatus.COMPLETED)]
        rejection_rate = (
            len([s for s in decided if s == SubmissionStatus.REJECTED]) / len(decided) if decided else None
        )

        return {
            "byStatus": {status.value: count for status, count in by_status_rows},
            "byTemplate": {code: count for code, count in by_template_rows},
            "avgTurnaroundHours": avg_turnaround,
            "backlog": [
                {"id": str(b.id), "code": b.code, "templateName": b.template.name, "status": b.status,
                 "submittedAt": b.submitted_at}
                for b in backlog_rows
            ],
            "rejectionRate30d": rejection_rate,
        }


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
