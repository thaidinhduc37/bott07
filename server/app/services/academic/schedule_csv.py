"""Pure CSV parsing for class-session and exam schedules. Port of the
(deleted) NestJS `schedule-csv.parser.ts` — no DB access, no FastAPI/Depends,
so the exact same functions back both the CSV-import endpoint and any future
seed script (matches the reference's own reason for keeping this DI-free).

Design, preserved from the porting notes:
- `check_headers()` validates required columns up front (fail fast on a
  structurally wrong file).
- Per-row validation accumulates `RowError` — one bad row does not abort
  the whole parse; the caller decides whether to reject the batch
  wholesale (`allow_partial=False`, the default) or import the good rows.
- All date+time pairs are authored in VN local time and converted to UTC
  via `zoneinfo` — storing the raw string directly would let Postgres
  interpret it as UTC and silently shift by 7 hours.
- `detect_conflicts()` sorts by start time then does a windowed scan,
  early-breaking once a later row's start is at/after the current row's
  end (rows are sorted, so nothing after that point can overlap).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

SESSION_TYPE_LABELS: dict[str, str] = {
    "lý thuyết": "LY_THUYET",
    "thực hành": "THUC_HANH",
    "kiểm tra giữa kỳ": "KIEM_TRA_GIUA_KY",
    "ôn tập": "ON_TAP",
    "học bù": "HOC_BU",
}

SCHEDULE_STATUS_LABELS: dict[str, str] = {
    "đã lên lịch": "SCHEDULED",
    "nghỉ lễ": "HOLIDAY",
    "đã hủy": "CANCELLED",
    "hủy": "CANCELLED",
    "hoàn thành": "COMPLETED",
}

EXAM_STATUS_LABELS: dict[str, str] = {
    "đã công bố": "PUBLISHED",
    "nháp": "DRAFT",
    "đã hủy": "CANCELLED",
    "hủy": "CANCELLED",
}

_SCHEDULE_REQUIRED_COLS = [
    "schedule_id", "academic_year", "semester", "class_code", "course_code", "course_name",
    "credits", "session_date", "start_period", "end_period", "start_time", "end_time",
    "room", "session_type", "status",
]

_EXAM_REQUIRED_COLS = [
    "exam_id", "academic_year", "semester", "class_code", "course_code", "course_name",
    "credits", "exam_date", "exam_shift", "start_time", "duration_minutes", "room",
    "exam_format", "status",
]


def map_exam_format(raw: str) -> str:
    """Exam format is free Vietnamese text in the source CSV, not a closed
    vocabulary — heuristically mapped into the coarse `ExamFormat` enum while
    the raw text is preserved separately (`exam_format_raw`)."""
    r = raw.strip().lower()
    if "trắc nghiệm" in r and "và" not in r:
        return "TRAC_NGHIEM"
    if "thực hành" in r and "và" not in r:
        return "THUC_HANH"
    if "tự luận" in r and "và" not in r:
        return "TU_LUAN"
    if "và" in r or "kết hợp" in r:
        return "KET_HOP"
    if "trắc nghiệm" in r:
        return "TRAC_NGHIEM"
    if "thực hành" in r:
        return "THUC_HANH"
    if "tự luận" in r:
        return "TU_LUAN"
    return "TU_LUAN"


@dataclass
class RowError:
    line: int
    column: str
    message: str


@dataclass
class ParseResult:
    rows: list[dict] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def _strip_bom_and_read(text: str) -> list[dict]:
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def check_headers(fieldnames: list[str] | None, required: list[str]) -> list[str]:
    have = set((fieldnames or []))
    return [c for c in required if c not in have]


def _parse_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _parse_time(value: str) -> time | None:
    m = re.match(r"^(\d{1,2}):(\d{2})$", value.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return time(hour=h, minute=mi)


def _combine_vn_to_utc(d: date, t: time) -> datetime:
    local = datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=VN_TZ)
    return local.astimezone(ZoneInfo("UTC"))


def parse_schedule_csv(text: str) -> ParseResult:
    result = ParseResult()
    try:
        raw_reader_check = csv.DictReader(io.StringIO(text[1:] if text.startswith("﻿") else text))
        missing = check_headers(raw_reader_check.fieldnames, _SCHEDULE_REQUIRED_COLS)
    except Exception:
        missing = _SCHEDULE_REQUIRED_COLS
    if missing:
        result.errors.append(RowError(line=1, column=",".join(missing), message="Thiếu cột bắt buộc trong file CSV"))
        return result

    for i, raw in enumerate(_strip_bom_and_read(text)):
        line = i + 2  # header is line 1
        errs: list[RowError] = []

        credits = _parse_int(raw.get("credits"))
        if credits is None:
            errs.append(RowError(line, "credits", "Số tín chỉ không hợp lệ"))

        week_number = _parse_int(raw.get("week_number"))

        start_period = _parse_int(raw.get("start_period"))
        end_period = _parse_int(raw.get("end_period"))
        if start_period is None or end_period is None:
            errs.append(RowError(line, "start_period/end_period", "Tiết học không hợp lệ"))
        elif end_period < start_period:
            errs.append(RowError(line, "end_period", "Tiết kết thúc phải sau tiết bắt đầu"))

        session_date = _parse_date(raw.get("session_date", ""))
        if session_date is None:
            errs.append(RowError(line, "session_date", "Ngày học không hợp lệ (định dạng YYYY-MM-DD)"))

        start_time = _parse_time(raw.get("start_time", ""))
        end_time = _parse_time(raw.get("end_time", ""))
        if start_time is None or end_time is None:
            errs.append(RowError(line, "start_time/end_time", "Giờ học không hợp lệ (định dạng HH:MM)"))

        session_type_raw = (raw.get("session_type") or "").strip().lower()
        session_type = SESSION_TYPE_LABELS.get(session_type_raw)
        if session_type is None:
            errs.append(RowError(line, "session_type", f'Loại buổi học không hợp lệ: "{raw.get("session_type")}"'))

        status_raw = (raw.get("status") or "").strip().lower()
        status = SCHEDULE_STATUS_LABELS.get(status_raw)
        if status is None:
            errs.append(RowError(line, "status", f'Trạng thái không hợp lệ: "{raw.get("status")}"'))

        for required_str in ("schedule_id", "academic_year", "semester", "class_code", "course_code", "room"):
            if not (raw.get(required_str) or "").strip():
                errs.append(RowError(line, required_str, f'Thiếu giá trị cho cột "{required_str}"'))

        if errs:
            result.errors.extend(errs)
            continue

        starts_at = _combine_vn_to_utc(session_date, start_time)
        ends_at = _combine_vn_to_utc(session_date, end_time)
        if ends_at <= starts_at:
            result.errors.append(RowError(line, "end_time", "Giờ kết thúc phải sau giờ bắt đầu"))
            continue

        result.rows.append({
            "_line": line,
            "external_id": raw["schedule_id"].strip(),
            "academic_year": raw["academic_year"].strip(),
            "semester": raw["semester"].strip(),
            "class_code": raw["class_code"].strip(),
            "course_code": raw["course_code"].strip(),
            "course_name": (raw.get("course_name") or "").strip(),
            "credits": credits,
            "session_date": session_date,
            "week_number": week_number,
            "start_period": start_period,
            "end_period": end_period,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "room": raw["room"].strip(),
            "building": (raw.get("building") or "").strip() or None,
            "instructor": (raw.get("instructor") or "").strip() or None,
            "delivery_mode": (raw.get("delivery_mode") or "").strip() or None,
            "session_type": session_type,
            "status": status,
            "note": (raw.get("note") or "").strip() or None,
        })

    return result


def parse_exam_csv(text: str) -> ParseResult:
    result = ParseResult()
    try:
        raw_reader_check = csv.DictReader(io.StringIO(text[1:] if text.startswith("﻿") else text))
        missing = check_headers(raw_reader_check.fieldnames, _EXAM_REQUIRED_COLS)
    except Exception:
        missing = _EXAM_REQUIRED_COLS
    if missing:
        result.errors.append(RowError(line=1, column=",".join(missing), message="Thiếu cột bắt buộc trong file CSV"))
        return result

    for i, raw in enumerate(_strip_bom_and_read(text)):
        line = i + 2
        errs: list[RowError] = []

        credits = _parse_int(raw.get("credits"))
        duration_minutes = _parse_int(raw.get("duration_minutes"))
        if duration_minutes is None or duration_minutes <= 0:
            errs.append(RowError(line, "duration_minutes", "Thời lượng thi không hợp lệ"))

        candidate_count = _parse_int(raw.get("candidate_count"))

        exam_date = _parse_date(raw.get("exam_date", ""))
        if exam_date is None:
            errs.append(RowError(line, "exam_date", "Ngày thi không hợp lệ (định dạng YYYY-MM-DD)"))

        start_time = _parse_time(raw.get("start_time", ""))
        if start_time is None:
            errs.append(RowError(line, "start_time", "Giờ thi không hợp lệ (định dạng HH:MM)"))

        status_raw = (raw.get("status") or "").strip().lower()
        status = EXAM_STATUS_LABELS.get(status_raw)
        if status is None:
            errs.append(RowError(line, "status", f'Trạng thái không hợp lệ: "{raw.get("status")}"'))

        for required_str in ("exam_id", "academic_year", "semester", "class_code", "course_code", "room", "exam_format"):
            if not (raw.get(required_str) or "").strip():
                errs.append(RowError(line, required_str, f'Thiếu giá trị cho cột "{required_str}"'))

        if errs:
            result.errors.extend(errs)
            continue

        starts_at = _combine_vn_to_utc(exam_date, start_time)
        ends_at = starts_at + timedelta(minutes=duration_minutes)
        exam_format_raw = raw["exam_format"].strip()

        result.rows.append({
            "_line": line,
            "external_id": raw["exam_id"].strip(),
            "academic_year": raw["academic_year"].strip(),
            "semester": raw["semester"].strip(),
            "class_code": raw["class_code"].strip(),
            "course_code": raw["course_code"].strip(),
            "course_name": (raw.get("course_name") or "").strip(),
            "credits": credits,
            "exam_date": exam_date,
            "shift": (raw.get("exam_shift") or "").strip() or None,
            "starts_at": starts_at,
            "duration_minutes": duration_minutes,
            "ends_at": ends_at,
            "room": raw["room"].strip(),
            "building": (raw.get("building") or "").strip() or None,
            "exam_format": map_exam_format(exam_format_raw),
            "exam_format_raw": exam_format_raw,
            "allowed_materials": (raw.get("allowed_materials") or "").strip() or None,
            "candidate_count": candidate_count,
            "chief_proctor": (raw.get("chief_proctor") or "").strip() or None,
            "second_proctor": (raw.get("second_proctor") or "").strip() or None,
            "status": status,
            "note": (raw.get("note") or "").strip() or None,
        })

    return result


def detect_conflicts(rows: list[dict]) -> list[dict]:
    """Windowed overlap scan over parsed rows (schedule OR exam rows — both
    carry starts_at/ends_at/class_code/room; schedule rows additionally
    carry instructor). Sorted by start time; breaks early once a later row's
    start is at/after the current row's end, since nothing further out can
    overlap either."""
    conflicts: list[dict] = []
    sorted_rows = sorted(rows, key=lambda r: r["starts_at"])
    for i, a in enumerate(sorted_rows):
        for b in sorted_rows[i + 1:]:
            if b["starts_at"] >= a["ends_at"]:
                break
            if a["class_code"] == b["class_code"]:
                conflicts.append({"lineA": a["_line"], "lineB": b["_line"], "reason": "Trùng lịch của lớp"})
            if a.get("room") and a["room"] == b.get("room"):
                conflicts.append({"lineA": a["_line"], "lineB": b["_line"], "reason": f'Trùng phòng "{a["room"]}"'})
            instr_a = a.get("instructor") or a.get("chief_proctor")
            instr_b = b.get("instructor") or b.get("chief_proctor")
            if instr_a and instr_a == instr_b:
                conflicts.append({"lineA": a["_line"], "lineB": b["_line"], "reason": f'Trùng lịch của "{instr_a}"'})
    return conflicts


def sniff_is_exam(filename: str | None, content: str) -> bool:
    if filename and re.search(r"thi|exam", filename, re.IGNORECASE):
        return True
    stripped = content[1:] if content.startswith("﻿") else content
    return stripped.lstrip().startswith("exam_id")
