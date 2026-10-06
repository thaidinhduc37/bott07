"""Hằng số và hàm thuần dùng chung của dịch vụ biểu mẫu (nguồn tự điền, trạng thái sửa được, đổi ngày)."""


from __future__ import annotations

import re
import uuid

from starlette.requests import Request

from app.models.enums import SubmissionStatus
from app.core.security import ACCESS_COOKIE

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



def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
