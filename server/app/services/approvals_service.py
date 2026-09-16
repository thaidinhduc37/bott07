"""Approval engine: state machine + per-step access control + the
signature-composition side effect coupled to APPROVE. Port of the (deleted)
NestJS `approvals.service.ts` — the hardest piece of this port to get right,
per the porting notes:

- `TRANSITIONS` is the ONLY place that decides valid status changes. Every
  action not present for the submission's current status is rejected —
  this IS the "no skipping approval levels" enforcement.
- `can_act` is a triple check: right step, right step status, right
  assignee-or-unassigned — AND the caller must hold the step's role.
- APPROVE embeds the approver's signature and re-renders the WHOLE document
  from scratch every time (never patches an existing file) — "approving IS
  signing", not a separate step.
- REQUEST_REVISION clears the submission's `signed_path`/`signed_hash` —
  the student must re-sign after editing.
- REJECT is terminal — no `next_step_order`.
- 404-not-403 on `detail()`/`file_of()` (confirming a submission exists to
  someone with no matching step is itself a leak); 403 `NOT_YOUR_STEP` on
  `act()` (the caller reached this submission via a shared inbox, so its
  existence is already known — no anti-enumeration concern there).
- File writes happen BEFORE the DB transaction commits, same ordering as
  the reference — preserved, not "fixed".
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.deps import AuthenticatedUser
from app.models.enums import ApprovalActionType, NotificationType, RoleCode, StepStatus, SubmissionStatus
from app.models.forms import ApprovalAction, ApprovalStep, FormSubmission, FormTemplate, SubmissionSigning
from app.models.notifications import Notification
from app.models.users import StudentProfile, User
from app.security import ACCESS_COOKIE, hash_token
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.forms_service import FormsService
from app.services.signatures_service import SignaturesService
from app.services.storage_service import StorageService

# The ONLY table that decides which status transitions are legal. An action
# not present here for the submission's current status is always rejected.
TRANSITIONS: dict[str, set[SubmissionStatus]] = {
    "SUBMIT": {SubmissionStatus.DRAFT, SubmissionStatus.NEEDS_REVISION},
    "RESUBMIT": {SubmissionStatus.NEEDS_REVISION},
    "RECEIVE": {SubmissionStatus.SUBMITTED},
    "REQUEST_REVISION": {SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW},
    "REJECT": {SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW},
    "APPROVE": {SubmissionStatus.UNDER_REVIEW},
    "SIGN": {SubmissionStatus.DRAFT, SubmissionStatus.NEEDS_REVISION},
    "COMPLETE": {SubmissionStatus.APPROVED},
}

_ACTIVE_STEP_STATUSES = {StepStatus.PENDING, StepStatus.IN_PROGRESS}

_ACTION_LABELS = {
    "RECEIVE": "Đã tiếp nhận",
    "APPROVE": "Đã duyệt",
    "REJECT": "Đã từ chối",
    "REQUEST_REVISION": "Yêu cầu bổ sung",
    "COMPLETE": "Đã hoàn tất",
}

# Nhãn hành động dùng cho lịch sử xử lý (`detail().history`) — bao quát mọi
# giá trị `ApprovalActionType`, kể cả SUBMIT/RESUBMIT/SIGN xảy ra trước khi
# đơn tới tay cán bộ duyệt.
_ACTION_LOG_LABELS = {
    "SUBMIT": "Gửi trình ký",
    "RESUBMIT": "Gửi lại sau khi bổ sung",
    "RECEIVE": "Tiếp nhận",
    "REQUEST_REVISION": "Yêu cầu bổ sung",
    "REJECT": "Từ chối",
    "APPROVE": "Phê duyệt",
    "SIGN": "Ký",
    "COMPLETE": "Hoàn thành",
}

_STATUS_LABELS = {
    SubmissionStatus.DRAFT: "Bản nháp",
    SubmissionStatus.SUBMITTED: "Đã gửi trình ký",
    SubmissionStatus.UNDER_REVIEW: "Đang duyệt",
    SubmissionStatus.NEEDS_REVISION: "Yêu cầu bổ sung",
    SubmissionStatus.REJECTED: "Không được duyệt",
    SubmissionStatus.APPROVED: "Đã duyệt",
    SubmissionStatus.COMPLETED: "Đã hoàn thành",
}


def _notification_body(action: str, template_name: str, comment: str | None) -> str:
    base = {
        "RECEIVE": f'Đơn "{template_name}" của bạn đã được tiếp nhận xử lý.',
        "APPROVE": f'Đơn "{template_name}" của bạn đã được duyệt ở một cấp.',
        "REJECT": f'Đơn "{template_name}" của bạn đã bị từ chối.',
        "REQUEST_REVISION": f'Đơn "{template_name}" của bạn cần được bổ sung/chỉnh sửa.',
        "COMPLETE": f'Đơn "{template_name}" của bạn đã hoàn tất xử lý.',
    }.get(action, f'Đơn "{template_name}" của bạn đã được cập nhật.')
    if comment:
        base += f" Nhận xét: {comment}"
    return base


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


class ApprovalsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = StorageService()
        self.audit = AuditService(db)
        self.forms = FormsService(db)
        self.signatures = SignaturesService(db)

    # ------------------------------------------------------------- access

    @staticmethod
    def _can_act(user: AuthenticatedUser, current_step_order: int | None, step: ApprovalStep) -> bool:
        return (
            current_step_order is not None
            and current_step_order == step.step_order
            and step.status in _ACTIVE_STEP_STATUSES
            and (step.assignee_id is None or str(step.assignee_id) == str(user.id))
            and step.role_code.value in user.roles
        )

    # -------------------------------------------------------------- inbox

    async def inbox(self, user: AuthenticatedUser, *, done: bool) -> dict:
        if done:
            return await self._inbox_done(user)

        stmt = (
            select(FormSubmission)
            .options(
                selectinload(FormSubmission.template),
                selectinload(FormSubmission.owner).selectinload(User.student_profile),
                selectinload(FormSubmission.steps),
            )
            .where(FormSubmission.status.in_([
                SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW, SubmissionStatus.APPROVED,
            ]))
            .order_by(FormSubmission.submitted_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().unique().all()

        items = []
        for s in rows:
            matching_step = next(
                (
                    st for st in s.steps
                    if st.role_code.value in user.roles
                    and st.status in _ACTIVE_STEP_STATUSES
                    and (st.assignee_id is None or str(st.assignee_id) == str(user.id))
                    and st.step_order == s.current_step_order
                ),
                None,
            )
            if matching_step is not None:
                items.append(self._present_inbox_item(s, matching_step))

        return {"items": items}

    async def _inbox_done(self, user: AuthenticatedUser) -> dict:
        done_actions = {
            ApprovalActionType.APPROVE, ApprovalActionType.REJECT,
            ApprovalActionType.REQUEST_REVISION, ApprovalActionType.COMPLETE,
        }
        stmt = (
            select(ApprovalAction.submission_id)
            .where(ApprovalAction.actor_id == user.id, ApprovalAction.action.in_(done_actions))
            .distinct()
        )
        submission_ids = [r[0] for r in (await self.db.execute(stmt)).all()]
        if not submission_ids:
            return {"items": []}

        rows_stmt = (
            select(FormSubmission)
            .options(
                selectinload(FormSubmission.template),
                selectinload(FormSubmission.owner).selectinload(User.student_profile),
                selectinload(FormSubmission.steps),
            )
            .where(FormSubmission.id.in_(submission_ids))
            .order_by(FormSubmission.updated_at.desc())
        )
        rows = (await self.db.execute(rows_stmt)).scalars().unique().all()
        return {"items": [self._present_inbox_item(s, None) for s in rows]}

    @staticmethod
    def _present_inbox_item(s: FormSubmission, current_step: ApprovalStep | None) -> dict:
        profile = s.owner.student_profile
        return {
            "id": str(s.id), "code": s.code, "status": s.status,
            "statusLabel": _STATUS_LABELS[s.status],
            "submittedAt": s.submitted_at,
            "currentStepOrder": s.current_step_order,
            "currentStep": {
                "stepOrder": current_step.step_order, "title": current_step.title,
                "roleCode": current_step.role_code, "status": current_step.status,
                "decidedAt": current_step.decided_at, "comment": current_step.comment,
            } if current_step else None,
            "studentCode": profile.student_code if profile else None,
            "owner": {"id": str(s.owner.id), "fullName": s.owner.full_name},
            "template": {"code": s.template.code, "name": s.template.name},
        }

    # ------------------------------------------------------------- detail

    async def _load_with_access(self, id: str, user: AuthenticatedUser) -> FormSubmission:
        if not _is_uuid(id):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy đơn"})
        stmt = (
            select(FormSubmission)
            .options(
                selectinload(FormSubmission.template),
                selectinload(FormSubmission.owner).selectinload(User.student_profile).selectinload(StudentProfile.study_class),
                selectinload(FormSubmission.steps), selectinload(FormSubmission.actions).selectinload(ApprovalAction.actor),
                selectinload(FormSubmission.signings).selectinload(SubmissionSigning.signer),
            )
            .where(FormSubmission.id == id)
            # Same reasoning as documents_service.get(): act()/detail() are
            # often called on a submission that's already in this session's
            # identity map (e.g. detail() called right after act() mutated
            # and flushed it) — without populate_existing, SQLAlchemy would
            # return the cached instance with its already-loaded relationship
            # collections (actions/steps/signings) as they were BEFORE the
            # mutation, silently hiding the just-inserted row.
            .execution_options(populate_existing=True)
        )
        submission = (await self.db.execute(stmt)).scalar_one_or_none()
        if not submission:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy đơn"})

        # Access: caller must hold the role of ANY step on this submission,
        # even a completed/closed one — not just the currently-active step.
        has_any_matching_role = any(st.role_code.value in user.roles for st in submission.steps)
        if not has_any_matching_role:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy đơn"})
        return submission

    async def detail(self, id: str, user: AuthenticatedUser) -> dict:
        submission = await self._load_with_access(id, user)
        profile = submission.owner.student_profile
        return {
            "id": str(submission.id), "code": submission.code, "status": submission.status,
            "statusLabel": _STATUS_LABELS[submission.status],
            "currentStepOrder": submission.current_step_order,
            "createdAt": submission.created_at,
            "submittedAt": submission.submitted_at, "completedAt": submission.completed_at,
            "signedHash": submission.signed_hash,
            "hasFile": bool(submission.signed_path or submission.generated_path),
            "owner": {
                "fullName": submission.owner.full_name,
                "email": submission.owner.email,
                "studentCode": profile.student_code if profile else None,
                "className": profile.study_class.code if profile and profile.study_class else None,
            },
            "template": {"code": submission.template.code, "name": submission.template.name},
            "fields": submission.template.field_schema or [],
            "formData": submission.form_data, "profileSnapshot": submission.profile_snapshot,
            "steps": [
                {
                    "stepOrder": st.step_order, "title": st.title, "roleCode": st.role_code,
                    "status": st.status, "decidedAt": st.decided_at, "comment": st.comment,
                    "canAct": self._can_act(user, submission.current_step_order, st),
                }
                for st in sorted(submission.steps, key=lambda x: x.step_order)
            ],
            "history": [
                {
                    "action": a.action, "actionLabel": _ACTION_LOG_LABELS.get(a.action.value, a.action.value),
                    "actor": a.actor.full_name if a.actor else None, "stepOrder": a.step_order,
                    "fromStatus": a.from_status, "toStatus": a.to_status, "comment": a.comment,
                    "ipAddress": a.ip_address, "createdAt": a.created_at,
                }
                for a in sorted(submission.actions, key=lambda x: x.created_at)
            ],
            "signings": [
                {
                    "stepOrder": sg.step_order, "signedAt": sg.signed_at,
                    "hashBefore": sg.hash_before, "hashAfter": sg.hash_after,
                }
                for sg in sorted(submission.signings, key=lambda x: x.signed_at)
            ],
        }

    # ---------------------------------------------------------------- act

    async def act(
        self, id: str, action: ApprovalActionType, *, comment: str | None, pin: str | None,
        user: AuthenticatedUser, request: Request | None,
    ) -> dict:
        submission = await self._load_with_access(id, user)
        template = submission.template
        action_name = action.value

        allowed_statuses = TRANSITIONS.get(action_name, set())
        if submission.status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Không thể thực hiện thao tác này khi đơn đang ở trạng thái {submission.status.value}",
                    "code": "INVALID_TRANSITION",
                },
            )

        steps_by_order = {st.step_order: st for st in submission.steps}

        if action_name == "COMPLETE":
            last_order = max(steps_by_order) if steps_by_order else None
            step = steps_by_order.get(last_order) if last_order is not None else None
            if step is None:
                raise HTTPException(status_code=400, detail={"message": "Đơn chưa có bước duyệt nào", "code": "NO_STEPS"})
            allowed = step.role_code.value in user.roles or RoleCode.ADMIN.value in user.roles
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail={"message": "Bạn không có quyền hoàn tất đơn này", "code": "NOT_YOUR_STEP"},
                )
        else:
            step = steps_by_order.get(submission.current_step_order)
            if step is None or not self._can_act(user, submission.current_step_order, step):
                raise HTTPException(
                    status_code=403,
                    detail={"message": "Bạn không phải người xử lý bước hiện tại của đơn này", "code": "NOT_YOUR_STEP"},
                )
            # Claim the step to the first officer who acts on it — subsequent
            # actions on the same step are then restricted to that officer by
            # _can_act's assignee_id check.
            if step.assignee_id is None:
                step.assignee_id = user.id

        if action_name in ("REJECT", "REQUEST_REVISION") and not (comment and comment.strip()):
            raise HTTPException(
                status_code=400,
                detail={"message": "Vui lòng nhập nhận xét khi từ chối hoặc yêu cầu bổ sung", "code": "COMMENT_REQUIRED"},
            )

        from_status = submission.status
        now = datetime.now(timezone.utc)
        next_step_order: int | None = submission.current_step_order

        if action_name == "RECEIVE":
            step.status = StepStatus.IN_PROGRESS
            submission.status = SubmissionStatus.UNDER_REVIEW

        elif action_name == "REQUEST_REVISION":
            step.status = StepStatus.REVISION_REQUESTED
            step.decided_at = now
            step.comment = comment
            submission.status = SubmissionStatus.NEEDS_REVISION
            # Student must re-sign after editing.
            submission.signed_path = None
            submission.signed_hash = None
            next_step_order = None

        elif action_name == "REJECT":
            step.status = StepStatus.REJECTED
            step.decided_at = now
            step.comment = comment
            submission.status = SubmissionStatus.REJECTED
            next_step_order = None  # terminal

        elif action_name == "APPROVE":
            if not pin:
                raise HTTPException(status_code=400, detail={"message": "Cần nhập mã PIN để duyệt/ký", "code": "PIN_REQUIRED"})
            await self._assert_signed_by_approver(submission, template, step, pin=pin, user=user, request=request)

            step.status = StepStatus.APPROVED
            step.decided_at = now
            step.comment = comment

            remaining = sorted((o for o in steps_by_order if o > step.step_order))
            if remaining:
                submission.status = SubmissionStatus.SUBMITTED  # waiting on next approver's RECEIVE
                next_step_order = remaining[0]
            else:
                submission.status = SubmissionStatus.APPROVED
                next_step_order = None

        elif action_name == "COMPLETE":
            submission.status = SubmissionStatus.COMPLETED
            submission.completed_at = now
            next_step_order = None
            # ApprovalStep rows are intentionally NOT touched for COMPLETE.

        else:
            raise HTTPException(status_code=400, detail={"message": "Hành động không hợp lệ", "code": "INVALID_ACTION"})

        submission.current_step_order = next_step_order

        self.db.add(ApprovalAction(
            submission_id=submission.id, actor_id=user.id, action=action,
            step_order=step.step_order if action_name != "COMPLETE" else None,
            from_status=from_status, to_status=submission.status, comment=comment,
            ip_address=request.client.host if request and request.client else None,
        ))
        self.db.add(Notification(
            user_id=submission.owner_id, type=NotificationType.SUBMISSION_STATUS,
            title=f"{submission.code}: {_ACTION_LABELS.get(action_name, action_name)}",
            body=_notification_body(action_name, template.name, comment),
            link_to=f"/sinh-vien/don-cua-toi/{submission.id}",
        ))

        await self.audit.log(
            action=f"FORM_{action_name}", user_id=user.id, entity_type="FormSubmission",
            entity_id=str(submission.id), detail={"comment": comment}, request=request,
        )
        await self.db.commit()
        return await self.detail(id, user)

    # ----------------------------------------------------- approve+sign

    async def _assert_signed_by_approver(
        self, submission: FormSubmission, template: FormTemplate, step: ApprovalStep, *,
        pin: str, user: AuthenticatedUser, request: Request | None,
    ) -> None:
        active_sig = await self.signatures.get_active_for_user(user.id)
        if not active_sig:
            raise HTTPException(status_code=400, detail={"message": "Bạn chưa đăng ký chữ ký điện tử", "code": "NO_SIGNATURE"})

        auth = AuthService(self.db)
        pin_ok = await auth.verify_signature_pin(user.id, pin)
        if not pin_ok:
            await self.audit.log(
                action="FORM_APPROVE_FAILED", user_id=user.id, entity_type="FormSubmission",
                entity_id=str(submission.id), request=request,
            )
            await self.db.commit()
            raise HTTPException(status_code=401, detail={"message": "Mã PIN không đúng", "code": "BAD_PIN"})

        current_path = submission.signed_path or submission.generated_path
        hash_before = (
            hashlib.sha256(self.storage.absolute(current_path).read_bytes()).hexdigest()
            if current_path and self.storage.absolute(current_path).exists()
            else (submission.signed_hash or "")
        )

        # Gather EVERY prior signer's image (their exact historical image,
        # not necessarily their current active signature), plus this new one.
        signatures_by_slot = await self._gather_signatures(submission.id)
        image_bytes = self.signatures.read_image_bytes(active_sig)
        signed_at = datetime.now(timezone.utc)
        signatures_by_slot[str(step.step_order)] = {
            "image_bytes": image_bytes, "signed_by": user.full_name, "signed_at": signed_at,
        }

        # Re-render the WHOLE document from source data — never a patch.
        signed_bytes = self.forms.build_docx(submission, template, signatures=signatures_by_slot)
        signed_path, hash_after = self.storage.write_named(
            "generated-forms", f"{submission.code}-signed.docx", signed_bytes,
        )

        submission.signed_path = signed_path
        submission.signed_hash = hash_after
        await self.db.flush()

        raw_token = _extract_raw_token(request)
        self.db.add(SubmissionSigning(
            submission_id=submission.id, signer_id=user.id, signature_id=active_sig.id,
            hash_before=hash_before, hash_after=hash_after, step_order=step.step_order,
            ip_address=request.client.host if request and request.client else None,
            session_id=hash_token(raw_token)[:16] if raw_token else None,
        ))

    async def _gather_signatures(self, submission_id) -> dict[str, dict]:
        stmt = (
            select(SubmissionSigning)
            .options(selectinload(SubmissionSigning.signer))
            .where(SubmissionSigning.submission_id == submission_id)
            .order_by(SubmissionSigning.signed_at.asc())
        )
        signings = (await self.db.execute(stmt)).scalars().all()

        out: dict[str, dict] = {}
        for sg in signings:
            key = "owner" if sg.step_order is None else str(sg.step_order)
            image_bytes = None
            if sg.signature_id:
                sig = await self.signatures.get_image_by_id(str(sg.signature_id))
                if sig:
                    image_bytes = self.signatures.read_image_bytes(sig)
            out[key] = {
                "image_bytes": image_bytes,
                "signed_by": sg.signer.full_name if sg.signer else None,
                "signed_at": sg.signed_at,
            }
        return out

    # ------------------------------------------------------------ file_of

    async def file_of(self, id: str, user: AuthenticatedUser) -> tuple[str, str]:
        submission = await self._load_with_access(id, user)
        path = submission.signed_path or submission.generated_path
        if not path:
            raise HTTPException(status_code=404, detail={"message": "Đơn chưa có file"})
        abs_path = self.storage.absolute(path)
        if not abs_path.exists():
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy file trên đĩa"})
        suffix = "-da-ky" if submission.signed_path else ""
        return str(abs_path), f"{submission.code}{suffix}.docx"


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
