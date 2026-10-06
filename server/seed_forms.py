"""Phase 3 test-seed: all 7 `FormTemplate` rows (field_schema + approval_flow),
enough to smoke-test create -> sign -> submit -> approve -> approve ->
complete for `DON_XIN_NGHI_HOC`, and to exercise the other 6 templates'
rendering/validation logic. Idempotent (upsert by `code`), same convention
as `seed_phase1.py`.

The full `seed.py` (courses, schedules, documents, the real production
seed) is Phase 5's job — this script is intentionally scoped to just forms,
clearly separate so Phase 5 can absorb or replace it wholesale.

Run with:  .venv/Scripts/python.exe seed_forms.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.models.forms import FormTemplate

# ---------------------------------------------------------------- flows

LEAVE_FORM_FLOW = [
    {"order": 1, "roleCode": "APPROVER", "title": "LĐ PHÒNG QLHV"},
    {"order": 2, "roleCode": "ACADEMIC_MANAGER", "title": "LĐ PHÒNG QLĐT&BDNC"},
]

HOAN_THI_FLOW = [
    {"order": 1, "roleCode": "APPROVER", "title": "LĐ PHÒNG QLHV"},
    {"order": 2, "roleCode": "ACADEMIC_MANAGER", "title": "LĐ PHÒNG QLĐT"},
]

BO_SUNG_HOAN_THI_FLOW = [
    {"order": 1, "roleCode": "APPROVER", "title": "LÃNH ĐẠO PHÒNG QLHV"},
    {"order": 2, "roleCode": "ACADEMIC_MANAGER", "title": "LÃNH ĐẠO PHÒNG QLĐT&BDNC"},
]

HOC_LAI_FLOW = [
    {"order": 1, "roleCode": "APPROVER", "title": "LÃNH ĐẠO PHÒNG QLHV"},
    {"order": 2, "roleCode": "ACADEMIC_MANAGER", "title": "LÃNH ĐẠO PHÒNG QLĐT&BDNC"},
]

# Only DON_XIN_HOC_BO_SUNG has a 3rd step (DEPARTMENT_HEAD) — order deduced
# from the original document's signature-column layout (leftmost = "LĐ
# KHOA"), still unconfirmed by Phòng Đào tạo per the porting notes; kept as
# order:3 to match.
HOC_BO_SUNG_FLOW = [
    {"order": 1, "roleCode": "APPROVER", "title": "LĐ PHÒNG QLHV"},
    {"order": 2, "roleCode": "ACADEMIC_MANAGER", "title": "LĐ PHÒNG QLĐT&BDNC"},
    {"order": 3, "roleCode": "DEPARTMENT_HEAD", "title": "LĐ KHOA"},
]

CAI_THIEN_FLOW = [
    {"order": 1, "roleCode": "APPROVER", "title": "LĐ PHÒNG QLHV"},
    {"order": 2, "roleCode": "ACADEMIC_MANAGER", "title": "LĐ PHÒNG QLĐT&BDNC"},
]


# --------------------------------------------------------------- schemas
#
# Only the per-template EXTRA fields (beyond the universal 7-field identity
# autofill, which is resolved separately and never declared here).

TEMPLATES = [
    {
        "code": "DON_XIN_NGHI_HOC",
        "name": "Đơn xin phép nghỉ học (1-3 ngày)",
        "description": "Áp dụng cho những trường hợp xin nghỉ học từ 01 đến 03 ngày.",
        "fields": [
            {"key": "leaveFrom", "label": "Nghỉ từ ngày", "type": "date", "required": True},
            {"key": "leaveTo", "label": "Đến ngày", "type": "date", "required": True},
            {"key": "courseCode", "label": "Học phần liên quan (nếu có)", "type": "text", "required": False, "maxLength": 100},
            {"key": "reason", "label": "Lý do", "type": "textarea", "required": True, "maxLength": 2000},
        ],
        "flow": LEAVE_FORM_FLOW,
    },
    {
        "code": "DON_XIN_NGHI_HOC_TREN_3",
        "name": "Đơn xin nghỉ học (trên 3 ngày)",
        "description": "Áp dụng cho những trường hợp xin nghỉ học trên 03 ngày.",
        "fields": [
            {"key": "leaveFrom", "label": "Nghỉ từ ngày", "type": "date", "required": True},
            {"key": "leaveTo", "label": "Đến ngày", "type": "date", "required": True},
            {"key": "reason", "label": "Lý do", "type": "textarea", "required": True, "maxLength": 2000},
        ],
        "flow": LEAVE_FORM_FLOW,
    },
    {
        "code": "DON_XIN_HOAN_THI",
        "name": "Đơn xin hoãn thi kết thúc học phần",
        "description": None,
        "fields": [
            {"key": "hocKy", "label": "Học kỳ", "type": "text", "required": True, "maxLength": 20},
            {"key": "namHoc", "label": "Năm học", "type": "text", "required": True, "maxLength": 20},
            {"key": "ngayThi", "label": "Ngày thi", "type": "date", "required": True},
            {"key": "hocPhan", "label": "Học phần", "type": "text", "required": True, "maxLength": 200},
            {"key": "lyDo", "label": "Lý do", "type": "textarea", "required": True, "maxLength": 2000},
        ],
        "flow": HOAN_THI_FLOW,
    },
    {
        "code": "DON_BO_SUNG_LI_DO_HOAN_THI",
        "name": "Đơn xin thi bổ sung",
        "description": None,
        "fields": [
            {"key": "hocPhan", "label": "Học phần", "type": "text", "required": True, "maxLength": 200},
            {"key": "ngayThi", "label": "Ngày thi", "type": "date", "required": True},
        ],
        "flow": BO_SUNG_HOAN_THI_FLOW,
    },
    {
        "code": "DON_XIN_HOC_LAI",
        "name": "Đơn xin học lại",
        "description": None,
        "fields": [
            {"key": "lanThuMayXinHoc", "label": "Lần thứ", "type": "text", "required": True, "maxLength": 10},
            {"key": "hocPhan", "label": "Học phần", "type": "text", "required": True, "maxLength": 200},
            {"key": "lanThi", "label": "Lần thi", "type": "text", "required": True, "maxLength": 10},
            {"key": "lanHoc", "label": "Lần học", "type": "text", "required": True, "maxLength": 10},
            {"key": "diemThi", "label": "Điểm thi", "type": "text", "required": True, "maxLength": 10},
        ],
        "flow": HOC_LAI_FLOW,
    },
    {
        "code": "DON_XIN_HOC_BO_SUNG",
        "name": "Đơn xin học bổ sung",
        "description": "Áp dụng khi học viên nghỉ quá 20% số tiết quy định của học phần.",
        "fields": [
            {"key": "tenKhoa", "label": "Tên Khoa", "type": "text", "required": True, "maxLength": 200},
            {"key": "hocPhan", "label": "Học phần", "type": "text", "required": True, "maxLength": 200},
            {"key": "soTietQuyDinh", "label": "Tổng số tiết quy định", "type": "number", "required": True},
            {"key": "soTietDaHoc", "label": "Số tiết đã học", "type": "number", "required": True},
            {"key": "soTietNghi", "label": "Số tiết đã nghỉ", "type": "number", "required": True},
            {"key": "lyDo", "label": "Lý do", "type": "textarea", "required": True, "maxLength": 2000},
        ],
        "flow": HOC_BO_SUNG_FLOW,
    },
    {
        "code": "DON_HOC_CAI_THIEN",
        "name": "Đơn xin học, thi cải thiện",
        "description": None,
        "fields": [
            {"key": "hocKy", "label": "Học kỳ", "type": "text", "required": True, "maxLength": 20},
            {"key": "namHoc", "label": "Năm học", "type": "text", "required": True, "maxLength": 20},
            {"key": "soHocPhanDaThi", "label": "Số học phần đã dự thi", "type": "number", "required": False},
            {"key": "soHocPhanChuaDat", "label": "Số học phần chưa đạt", "type": "number", "required": False},
            {
                "key": "hocPhanList",
                "label": "Các học phần xin học/thi cải thiện",
                "type": "table",
                "required": True,
                "maxRows": 20,
                "columns": [
                    {"key": "tenHocPhan", "label": "Tên học phần"},
                    {"key": "soTinChi", "label": "Số tín chỉ"},
                    {"key": "diemDaDat", "label": "Điểm học phần đã đạt được"},
                ],
            },
        ],
        "flow": CAI_THIEN_FLOW,
    },
]


async def upsert_templates(db: AsyncSession) -> None:
    for t in TEMPLATES:
        row = (await db.execute(select(FormTemplate).where(FormTemplate.code == t["code"]))).scalar_one_or_none()
        if row is None:
            row = FormTemplate(
                code=t["code"], name=t["name"], description=t["description"],
                field_schema=t["fields"], template_path=f"server/storage/templates/{t['code']}.docx",
                approval_flow=t["flow"], is_active=True,
            )
            db.add(row)
            print(f"  + template {t['code']}")
        else:
            row.name = t["name"]
            row.description = t["description"]
            row.field_schema = t["fields"]
            row.approval_flow = t["flow"]
            row.is_active = True
            print(f"  = template {t['code']} (updated)")
    await db.flush()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        print("Seeding form templates...")
        await upsert_templates(db)
        await db.commit()
        print(f"Done. {len(TEMPLATES)} templates seeded.")


if __name__ == "__main__":
    asyncio.run(main())
