"""Kiểm tra dữ liệu đơn theo field_schema và các quy tắc chéo trường."""


from __future__ import annotations

from datetime import date

from fastapi import HTTPException



class ValidationMixin:
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
