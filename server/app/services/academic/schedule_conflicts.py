"""Kiểm tra trùng lịch dùng chung cho buổi học (Schedule) và ca thi (ExamSchedule).

Hai buổi "trùng" khi khoảng thời gian của chúng giao nhau
(`a.starts_at < b.ends_at and a.ends_at > b.starts_at`) VÀ rơi vào một trong các
trường hợp:

- ``CLASS``:   cùng lớp (``class_id``).
- ``ROOM``:    cùng phòng — so không phân biệt hoa thường, bỏ khoảng trắng thừa;
               chỉ xét khi phòng không rỗng và không phải chuỗi kiểu "Chưa xếp".
               Nếu hai bên thuộc tòa nhà khác nhau thì KHÔNG tính trùng (cùng tên
               phòng nhưng ở hai tòa nhà khác).
- ``LECTURER``: cùng giảng viên = cùng ``courses.lecturer_id`` (khác NULL). Ngoài
               ra vẫn giữ so tên ``instructor`` khi cả hai bên đều có tên — để
               bắt trường hợp người dạy thay được ghi tay mà chưa gắn tài khoản.

Ca thi cũng chiếm phòng/lớp nên buổi học phải đối chiếu với ``exam_schedules``
(và ngược lại) cho hai loại ``CLASS`` và ``ROOM``.

Mọi hàm ở đây đều trả danh sách dict mô tả buổi bị trùng (dạng camelCase) để
truyền thẳng vào lỗi 409 — không giữ object ORM để tránh lazy-load.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.academic import Course, ExamSchedule, Schedule

# Chuỗi phòng "chưa xếp" — không được tính là trùng phòng với ai.
_UNSET_ROOM_MARKERS = ("", "chưa xếp", "chưa xep")


def _normalize_room(room: str | None) -> str | None:
    """Chuẩn hóa tên phòng để so sánh: bỏ khoảng trắng thừa, viết thường.

    Trả None nếu phòng rỗng hoặc là chuỗi kiểu "Chưa xếp" (không tham gia so trùng)."""
    if room is None:
        return None
    r = room.strip().lower()
    # "Chưa xếp", "Chưa xếp phòng"… đều là chưa có phòng: không tham gia so trùng.
    if not r or r in _UNSET_ROOM_MARKERS or r.startswith(("chưa xếp", "chua xep")):
        return None
    return r


def _is_unset_room(room: str | None) -> bool:
    return _normalize_room(room) is None


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def _course_ref(course) -> dict | None:
    return {"code": course.code, "name": course.name} if course else None


def _class_ref(cls) -> dict | None:
    return {"code": cls.code} if cls else None


def _entry_dict(
    *, kind: str, entry_kind: str, row, course, cls,
) -> dict:
    """Một mục trong danh sách ``conflicts`` của lỗi 409."""
    return {
        "kind": kind,
        "entryKind": entry_kind,
        "id": str(row.id),
        "course": _course_ref(course),
        "class": _class_ref(cls),
        "room": row.room,
        "startsAt": row.starts_at.isoformat(),
        "endsAt": row.ends_at.isoformat(),
    }


def _conflicts_between(
    *,
    subj_kind: str,
    subj_class_id: str,
    subj_room: str | None,
    subj_building: str | None,
    subj_lecturer_id: str | None,
    subj_instructor: str | None,
    subj_start: datetime,
    subj_end: datetime,
    other_row,
    other_lecturer_id: str | None,
    other_instructor: str | None,
    other_start: datetime,
    other_end: datetime,
    other_room: str | None,
    other_building: str | None,
) -> list[str]:
    """Trả các loại trùng (CLASS/ROOM/LECTURER) giữa buổi này và một buổi khác.

    CLASS và ROOM áp cho cả đối chiếu với ca thi; LECTURER chỉ giữa hai buổi
    cùng loại (ca thi không có cột ``instructor``)."""
    if not _overlaps(subj_start, subj_end, other_start, other_end):
        return []
    kinds: list[str] = []
    # CLASS — cùng lớp.
    if str(subj_class_id) == str(other_row.class_id):
        kinds.append("CLASS")
    # ROOM — cùng phòng (không phân biệt hoa thường/khoảng trắng), nhưng chỉ khi
    # không phải "cùng tên phòng ở hai tòa nhà khác nhau".
    subj_room_norm = _normalize_room(subj_room)
    other_room_norm = _normalize_room(other_room)
    if subj_room_norm and subj_room_norm == other_room_norm:
        subj_b = (subj_building or "").strip().lower()
        other_b = (other_building or "").strip().lower()
        if not (subj_b and other_b and subj_b != other_b):
            kinds.append("ROOM")
    # LECTURER — cùng giảng viên (theo tài khoản) hoặc cùng tên người dạy.
    if subj_kind == "SESSION" and other_row is not None and type(other_row).__name__ == "Schedule":
        if subj_lecturer_id and subj_lecturer_id == str(other_lecturer_id or ""):
            kinds.append("LECTURER")
        elif (
            subj_instructor
            and other_instructor
            and subj_instructor.strip() == other_instructor.strip()
        ):
            kinds.append("LECTURER")
    return kinds


async def _load_other_rows(
    db: AsyncSession, *, start: datetime, end: datetime, exclude_id: str | None
) -> tuple[list[Schedule], list[ExamSchedule]]:
    """Nạp mọi buổi học + ca thi giao nhau với khoảng giờ, kèm course/class/lecturer."""
    s_stmt = (
        select(Schedule)
        .options(selectinload(Schedule.course), selectinload(Schedule.study_class))
        .where(Schedule.starts_at < end, Schedule.ends_at > start)
    )
    e_stmt = (
        select(ExamSchedule)
        .options(selectinload(ExamSchedule.course), selectinload(ExamSchedule.study_class))
        .where(ExamSchedule.starts_at < end, ExamSchedule.ends_at > start)
    )
    if exclude_id:
        s_stmt = s_stmt.where(Schedule.id != exclude_id)
        e_stmt = e_stmt.where(ExamSchedule.id != exclude_id)
    sessions = list((await db.execute(s_stmt)).scalars().unique().all())
    exams = list((await db.execute(e_stmt)).scalars().unique().all())
    return sessions, exams


def _lecturer_id_of(course) -> str | None:
    return str(course.lecturer_id) if course is not None and course.lecturer_id else None


async def find_conflicts(
    db: AsyncSession,
    *,
    subj_kind: str,
    class_id: str,
    room: str | None,
    building: str | None,
    course_id: str | None,
    instructor: str | None,
    starts_at: datetime,
    ends_at: datetime,
    exclude_id: str | None = None,
) -> list[dict]:
    """Kiểm tra trùng cho một buổi (SESSION) hoặc ca thi (EXAM) đang tạo/sửa.

    ``course_id`` dùng để lấy ``lecturer_id`` thật của giảng viên (khác NULL).
    Trả danh sách dict (đã gán ``kind``), rỗng nếu không trùng."""
    # Lấy lecturer_id của môn đang xét (nếu có).
    subj_lecturer_id: str | None = None
    if course_id:
        c = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
        subj_lecturer_id = _lecturer_id_of(c)

    sessions, exams = await _load_other_rows(db, start=starts_at, end=ends_at, exclude_id=exclude_id)

    conflicts: list[dict] = []

    def consider(row, course, cls, entry_kind: str, instructor_val: str | None):
        kinds = _conflicts_between(
            subj_kind=subj_kind,
            subj_class_id=class_id,
            subj_room=room,
            subj_building=building,
            subj_lecturer_id=subj_lecturer_id,
            subj_instructor=instructor,
            subj_start=starts_at,
            subj_end=ends_at,
            other_row=row,
            other_lecturer_id=_lecturer_id_of(course),
            other_instructor=instructor_val,
            other_start=row.starts_at,
            other_end=row.ends_at,
            other_room=row.room,
            other_building=row.building,
        )
        if kinds:
            conflicts.append(_entry_dict(kind=kinds[0], entry_kind=entry_kind, row=row, course=course, cls=cls))

    for s in sessions:
        consider(s, s.course, s.study_class, "SESSION", s.instructor)
    for e in exams:
        consider(e, e.course, e.study_class, "EXAM", None)

    return conflicts


def conflict_message(conflicts: list[dict]) -> str:
    """Tóm tắt tiếng Việt cho lỗi 409, liệt kê buổi bị trùng."""
    if not conflicts:
        return "Lịch bị trùng"
    parts: list[str] = []
    for c in conflicts:
        kind = c.get("kind")
        entry = c.get("entryKind")
        course = c.get("course") or {}
        cls = c.get("class") or {}
        room = c.get("room")
        start = c.get("startsAt")
        end = c.get("endsAt")
        what = "ca thi" if entry == "EXAM" else "buổi học"
        label = f"môn {course.get('code') or course.get('name') or ''}".strip()
        cls_label = f" lớp {cls.get('code')}" if cls.get("code") else ""
        time_label = ""
        try:
            if start and end:
                # `startsAt`/`endsAt` là chuỗi ISO (UTC) — đổi về giờ Việt Nam để đọc.
                vn = ZoneInfo("Asia/Ho_Chi_Minh")
                a = datetime.fromisoformat(start).astimezone(vn)
                b = datetime.fromisoformat(end).astimezone(vn)
                time_label = f" {a:%H:%M}–{b:%H:%M}"
        except (ValueError, TypeError):
            pass
        reason = {"CLASS": "cùng lớp", "ROOM": f"cùng phòng {room}", "LECTURER": "cùng giảng viên"}.get(kind, "trùng")
        parts.append(f"{reason} với {what} {label}{cls_label}{time_label}".replace("  ", " ").strip())
    return "Lịch bị trùng: " + "; ".join(parts)
