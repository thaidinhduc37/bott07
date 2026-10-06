"""Tiện ích dùng chung của dịch vụ danh mục (lớp, môn, học viên)."""


from __future__ import annotations

import re
import uuid

from fastapi import HTTPException


_CODE_RE = re.compile(r"^[A-Z0-9_-]{1,30}$")


def _parse_uuid(value: str, label: str) -> str:
    """Id không hợp lệ UUID → 404 (yêu cầu của brief: không được 500)."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=404, detail={"message": f"Không tìm thấy {label}"}) from exc
