"""Ký, nộp và kiểm chứng đơn."""


from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.enums import ApprovalActionType, NotificationType, RoleCode, StepStatus, SubmissionStatus
from app.models.forms import (
    ApprovalAction,
    ApprovalStep,
    SubmissionSigning,
)
from app.models.notifications import Notification
from app.models.users import Role, User, UserRole
from app.core.security import hash_token
from app.services.accounts.auth_service import AuthService

from app.services.forms.forms_common import (
    EDITABLE_STATUSES,
    _extract_raw_token,
)

class SigningMixin:
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
