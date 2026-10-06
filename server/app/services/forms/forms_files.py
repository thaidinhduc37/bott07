"""Tệp đính kèm, dựng bản in .docx và tải tệp của đơn."""


from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.forms import (
    FormSubmission,
    FormTemplate,
    SubmissionAttachment,
)
from app.services.forms.docx_renderer import (
    OWNER_SIGNATURE_TITLE,
    RENDERER_VERSION,
    SignatureSlot,
    docx_renderer_version,
    render_form,
)
from app.services.forms.form_layouts import layout_for
from app.services.documents.storage_service import StorageError

from app.services.forms.forms_common import (
    _convert_iso_dates,
)

class FilesMixin:
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

    # ------------------------------------------------------------ file_of

    async def _refresh_stale_draft(self, submission: FormSubmission, template: FormTemplate) -> None:
        """Đơn CHƯA KÝ có tệp dựng bằng định dạng cũ thì dựng lại theo định dạng hiện hành khi mở xem.

        Chỉ áp dụng khi đơn chưa từng ký (không có `signed_path`/`signed_hash`): tệp của đơn đã ký gắn với mã
        băm trong chữ ký nên tuyệt đối không được thay. Nội dung (dữ liệu đơn) không đổi, chỉ trình bày."""
        if submission.signed_path or submission.signed_hash or not submission.generated_path:
            return
        abs_path = self.storage.absolute(submission.generated_path)
        if abs_path.exists() and docx_renderer_version(abs_path) == RENDERER_VERSION:
            return
        data = self.build_docx(submission, template, signatures={})
        relative_path, file_hash = self._write_generated(f"{submission.code}.docx", data)
        submission.generated_path = relative_path
        submission.generated_hash = file_hash
        submission.generated_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def file_of(self, id: str, user: AuthenticatedUser, variant: str | None) -> tuple[str, str]:
        submission, template = await self._load_owned(id, user.id)
        await self._refresh_stale_draft(submission, template)
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
