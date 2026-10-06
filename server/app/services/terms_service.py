"""Học kỳ và thời khóa biểu theo học phần của học viên.

Mỗi dòng lịch học / ca thi mang (năm học, học kỳ). Từ đó dựng:
  * danh sách học kỳ của lớp học viên (kèm khoảng ngày và học kỳ hiện tại),
  * danh sách "môn đã đăng ký" trong một học kỳ: tín chỉ, giảng viên, khoảng ngày và các khung giờ lặp lại.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.academic import Course, ExamSchedule, Schedule
from app.models.enums import ScheduleStatus
from app.models.users import StudentProfile
from app.services.schedules_service import SESSION_TYPE_LABEL, SchedulesService, _exam_opts

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
WEEKDAY_LABEL = {1: "Thứ 2", 2: "Thứ 3", 3: "Thứ 4", 4: "Thứ 5", 5: "Thứ 6", 6: "Thứ 7", 7: "Chủ nhật"}


def _local(dt: datetime) -> datetime:
    return dt.astimezone(VN_TZ)


class TermsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _class_id(self, user_id: str):
        profile = (
            await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
        ).scalar_one_or_none()
        return profile.class_id if profile else None

    async def my_terms(self, user_id: str) -> dict:
        class_id = await self._class_id(user_id)
        if class_id is None:
            return {"terms": [], "current": None}
        spans: dict[tuple[str, str], list[date]] = defaultdict(list)
        for model, col in ((Schedule, Schedule.session_date), (ExamSchedule, ExamSchedule.exam_date)):
            for year, sem, d in (
                await self.db.execute(select(model.academic_year, model.semester, col).where(model.class_id == class_id))
            ).all():
                spans[(year.strip(), sem.strip())].append(d)

        today = datetime.now(VN_TZ).date()
        terms = []
        for (year, sem), days in spans.items():
            terms.append(
                {"academicYear": year, "semester": sem, "from": min(days).isoformat(), "to": max(days).isoformat(),
                 "containsToday": min(days) <= today <= max(days)}
            )
        # Mới nhất trước.
        terms.sort(key=lambda t: (t["academicYear"], t["semester"]), reverse=True)
        current = next((t for t in terms if t["containsToday"]), terms[0] if terms else None)
        return {"terms": terms, "current": {"academicYear": current["academicYear"], "semester": current["semester"]} if current else None}

    async def my_enrollments(self, user_id: str, year: str | None, semester: str | None) -> dict:
        class_id = await self._class_id(user_id)
        if class_id is None:
            return {"term": None, "totalCredits": 0, "items": []}
        if not year or not semester:
            current = (await self.my_terms(user_id))["current"]
            if current is None:
                return {"term": None, "totalCredits": 0, "items": []}
            year, semester = current["academicYear"], current["semester"]

        sessions = (
            await self.db.execute(
                select(Schedule)
                .options(selectinload(Schedule.course).selectinload(Course.lecturer))
                .where(
                    Schedule.class_id == class_id, Schedule.academic_year == year, Schedule.semester == semester,
                    Schedule.status != ScheduleStatus.CANCELLED,
                )
                .order_by(Schedule.starts_at.asc())
            )
        ).scalars().unique().all()
        exams = (
            await self.db.execute(
                select(ExamSchedule)
                .options(selectinload(ExamSchedule.course))
                .where(ExamSchedule.class_id == class_id, ExamSchedule.academic_year == year, ExamSchedule.semester == semester)
                .order_by(ExamSchedule.starts_at.asc())
            )
        ).scalars().unique().all()

        by_course: dict = {}
        for s in sessions:
            c = by_course.setdefault(s.course_id, {"course": s.course, "sessions": [], "exams": []})
            c["sessions"].append(s)
        for e in exams:
            c = by_course.setdefault(e.course_id, {"course": e.course, "sessions": [], "exams": []})
            c["exams"].append(e)

        items = []
        for entry in by_course.values():
            course = entry["course"]
            sess = entry["sessions"]
            # Khung giờ lặp lại: gom theo (thứ, giờ bắt đầu, giờ kết thúc, phòng, loại buổi).
            slots: dict = {}
            for s in sess:
                st, en = _local(s.starts_at), _local(s.ends_at)
                key = (st.isoweekday(), st.strftime("%H:%M"), en.strftime("%H:%M"), s.room, s.session_type)
                slot = slots.setdefault(key, {"count": 0})
                slot["count"] += 1
            slot_list = [
                {
                    "weekday": k[0], "weekdayLabel": WEEKDAY_LABEL[k[0]], "startTime": k[1], "endTime": k[2], "room": k[3],
                    "sessionTypeLabel": SESSION_TYPE_LABEL.get(k[4], str(getattr(k[4], "value", k[4]))), "sessionCount": v["count"],
                }
                for k, v in sorted(slots.items(), key=lambda kv: (kv[0][0], kv[0][1]))
            ]
            dates = [s.session_date for s in sess]
            lecturer = course.lecturer if course is not None and "lecturer" in course.__dict__ else None
            items.append(
                {
                    "course": {"id": str(course.id), "code": course.code, "name": course.name, "credits": course.credits},
                    "lecturer": {"id": str(lecturer.id), "name": lecturer.full_name} if lecturer else None,
                    "firstDate": min(dates).isoformat() if dates else None,
                    "lastDate": max(dates).isoformat() if dates else None,
                    "sessionCount": len(sess),
                    "slots": slot_list,
                    "exam": (
                        {"date": entry["exams"][0].exam_date.isoformat(), "room": entry["exams"][0].room,
                         "startsAt": entry["exams"][0].starts_at.isoformat()}
                        if entry["exams"] else None
                    ),
                }
            )
        items.sort(key=lambda x: x["course"]["code"])
        return {
            "term": {"academicYear": year, "semester": semester},
            "totalCredits": sum(i["course"]["credits"] for i in items),
            "items": items,
        }

    async def my_exams(self, user_id: str, year: str | None, semester: str | None) -> dict:
        """Lịch thi của học viên trong một học kỳ, kèm số liệu tóm tắt (số môn thi, tổng tín chỉ)."""
        class_id = await self._class_id(user_id)
        empty = {"term": None, "examCount": 0, "totalCredits": 0, "upcomingCount": 0, "items": []}
        if class_id is None:
            return empty
        if not year or not semester:
            current = (await self.my_terms(user_id))["current"]
            if current is None:
                return empty
            year, semester = current["academicYear"], current["semester"]

        exams = (
            await self.db.execute(
                select(ExamSchedule)
                .options(*_exam_opts())
                .where(ExamSchedule.class_id == class_id, ExamSchedule.academic_year == year, ExamSchedule.semester == semester)
                .order_by(ExamSchedule.starts_at.asc())
            )
        ).scalars().unique().all()

        now = datetime.now(VN_TZ)
        courses = {e.course_id: e.course for e in exams if e.course is not None}
        items = []
        for e in exams:
            p = SchedulesService._present_exam(e)
            items.append(
                {
                    "id": p["id"], "course": p["course"],
                    "lecturer": p.get("lecturer"),
                    "examDate": p["examDate"], "startsAt": p["startsAt"], "endsAt": p["endsAt"],
                    "shift": p["shift"], "durationMinutes": p["durationMinutes"],
                    "room": p["room"], "building": p["building"],
                    "examFormat": p["examFormat"], "formatLabel": p["formatLabel"],
                    "allowedMaterials": p["allowedMaterials"], "candidateCount": p["candidateCount"],
                    "status": p["status"],
                    "upcoming": e.starts_at.astimezone(VN_TZ) >= now,
                }
            )
        return {
            "term": {"academicYear": year, "semester": semester},
            "examCount": len(items),
            "totalCredits": sum(c.credits for c in courses.values()),
            "upcomingCount": sum(1 for i in items if i["upcoming"]),
            "items": items,
        }
