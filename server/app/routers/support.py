"""Trang Hỗ trợ của học viên: hướng dẫn thủ tục (dựng từ các mẫu đơn đang bật), nơi liên hệ và câu hỏi thường gặp.

Phần thủ tục luôn khớp với hệ thống vì lấy thẳng từ `form_templates` (luồng duyệt, các ô phải điền). Nơi liên hệ và
câu hỏi thường gặp nằm ở `server/data/support.json` để người quản trị sửa mà không cần đụng mã; đọc lại tệp mỗi
lần gọi (tệp nhỏ) nên sửa xong chỉ cần tải lại trang.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.models.forms import FormTemplate

router = APIRouter(prefix="/support", tags=["support"])

_DATA = Path(__file__).resolve().parents[2] / "data" / "support.json"


def _load() -> dict:
    try:
        return json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Tệp thiếu hoặc hỏng: trang vẫn hiện phần thủ tục, chỉ thiếu liên hệ và câu hỏi.
        return {}


def _clean_contact(c: dict) -> dict:
    # Chỉ trả các trường có giá trị — trang ẩn dòng trống thay vì hiện ô rỗng.
    out = {"name": str(c.get("name", "")).strip(), "role": str(c.get("role", "")).strip()}
    for key in ("email", "phone", "location", "hours"):
        value = str(c.get(key, "") or "").strip()
        if value:
            out[key] = value
    return out


@router.get("/guide")
async def guide(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    templates = (
        await db.execute(select(FormTemplate).where(FormTemplate.is_active.is_(True)).order_by(FormTemplate.name.asc()))
    ).scalars().all()

    procedures = []
    for t in templates:
        fields = [f for f in (t.field_schema or []) if not f.get("autofill")]
        procedures.append(
            {
                "code": t.code,
                "name": t.name,
                "description": t.description,
                "approvalSteps": [
                    {"order": s.get("order"), "title": s.get("title")}
                    for s in sorted(t.approval_flow or [], key=lambda s: s.get("order", 0))
                ],
                # Các ô học viên phải tự điền; thông tin lấy từ hồ sơ thì không cần liệt kê.
                "fields": [
                    {"label": f.get("label"), "required": bool(f.get("required"))}
                    for f in fields
                ],
            }
        )

    data = _load()
    return {
        "procedures": procedures,
        "contacts": [_clean_contact(c) for c in data.get("contacts", [])],
        "faq": [
            {"q": str(i.get("q", "")).strip(), "a": str(i.get("a", "")).strip()}
            for i in data.get("faq", [])
            if i.get("q") and i.get("a")
        ],
    }
