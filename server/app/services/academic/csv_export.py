"""Xuất CSV cho Excel: UTF-8 có BOM, và vô hiệu hóa công thức (ô bắt đầu bằng = + - @ bị Excel hiểu là công thức)."""

from __future__ import annotations

import csv
import io
import re

from fastapi.responses import Response

_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIX) else text


def csv_response(filename: str, header: list[str], rows: list[list[object]]) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_safe(v) for v in row])
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "danh-sach"
    return Response(
        content=("﻿" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
