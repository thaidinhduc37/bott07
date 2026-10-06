"""Kế hoạch ôn thi — dựng từ lịch thi của lớp + giáo trình đã nạp + kết quả ôn tập.

Hoàn toàn tất định, không gọi LLM: vẫn chạy khi mô hình ngôn ngữ hết hạn mức,
và cùng dữ liệu thì luôn ra cùng kế hoạch (học viên không thấy lịch "nhảy").

Cách chia: các ngày từ hôm nay tới hôm trước ngày thi (tối đa `PLAN_DAYS`
ngày gần kỳ thi nhất) được chia đều cho các giáo trình của môn; ngày cuối cùng
luôn dành cho ôn câu sai + làm đề tổng hợp. Môn không có giáo trình thì mỗi
ngày chỉ gợi ý ôn câu sai và xem lại sổ tay.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.academic import ExamSchedule
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentType, ExamStatus, IndexStatus
from app.models.learning import QuizSession, QuizStatus, ReviewItem
from app.models.users import StudentProfile

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PLAN_DAYS = 14
HORIZON_DAYS = 120
RECENT_QUIZZES = 5

EXAM_FORMAT_LABEL = {
    "TRAC_NGHIEM": "Trắc nghiệm",
    "TU_LUAN": "Tự luận",
    "THUC_HANH": "Thực hành",
    "KET_HOP": "Kết hợp",
}


def _today_vn() -> date:
    return datetime.now(VN_TZ).date()


def readiness(quiz_count: int, avg_score: float | None, due: int) -> str:
    """Nhãn mức sẵn sàng. Cố ý thô: đây là lời nhắc, không phải đánh giá năng lực."""
    if quiz_count == 0:
        return "CHUA_ON"
    if avg_score is not None and avg_score >= 8 and due == 0:
        return "ON_DINH"
    return "CAN_ON_THEM"


def build_plan(today: date, exam_day: date, materials: list[dict]) -> list[dict]:
    """Chia các ngày trước kỳ thi cho từng giáo trình. Tách riêng để kiểm thử không cần DB.

    Trả về các KHOẢNG ngày (`from`..`to`, tính cả hai đầu): các ngày liền nhau cùng
    một việc được gộp lại, để môn một giáo trình không hiện 13 dòng giống hệt nhau.
    """
    days_left = (exam_day - today).days
    if days_left <= 0:
        return []
    start = max(today, exam_day - timedelta(days=PLAN_DAYS))
    days = [start + timedelta(days=i) for i in range((exam_day - start).days)]

    per_day: list[dict] = []
    study_days = days[:-1]  # ngày cuối trước thi dành cho tổng ôn
    for i, _ in enumerate(study_days):
        if materials:
            # Chia liên tục theo tỉ lệ: n ngày, m giáo trình -> mỗi giáo trình ~n/m ngày liền nhau.
            m = materials[min(i * len(materials) // len(study_days), len(materials) - 1)]
            per_day.append({"kind": "DOC", "title": f"Đọc và ôn: {m['title']}",
                            "documentId": m["id"], "suggestedTopic": m["title"]})
        else:
            per_day.append({"kind": "REVIEW", "title": "Ôn câu sai và xem lại sổ tay",
                            "documentId": None, "suggestedTopic": None})
    per_day.append({"kind": "FINAL", "title": "Tổng ôn: làm hết câu sai đến hạn và một đề tổng hợp",
                    "documentId": None, "suggestedTopic": None})

    segments: list[dict] = []
    for d, task in zip(days, per_day):
        last = segments[-1] if segments else None
        if last and last["kind"] == task["kind"] and last["documentId"] == task["documentId"] and task["kind"] != "FINAL":
            last["to"] = d.isoformat()
        else:
            segments.append({"from": d.isoformat(), "to": d.isoformat(), **task})
    return segments


class ExamPlanService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def plan(self, user_id: str) -> dict:
        profile = (
            await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
        ).scalar_one_or_none()
        if not profile or not profile.class_id:
            return {"today": _today_vn().isoformat(), "exams": [], "reason": "NO_CLASS"}

        now = datetime.now(timezone.utc)
        exams = (
            await self.db.execute(
                select(ExamSchedule)
                .options(selectinload(ExamSchedule.course))
                .where(
                    ExamSchedule.class_id == profile.class_id,
                    ExamSchedule.status == ExamStatus.PUBLISHED,
                    ExamSchedule.starts_at >= now,
                    ExamSchedule.starts_at < now + timedelta(days=HORIZON_DAYS),
                )
                .order_by(ExamSchedule.starts_at.asc())
            )
        ).scalars().all()
        if not exams:
            return {"today": _today_vn().isoformat(), "exams": []}

        course_ids = list({e.course_id for e in exams})

        docs = (
            await self.db.execute(
                select(Document.id, Document.title, Document.course_id)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .where(
                    Document.course_id.in_(course_ids),
                    Document.document_type == DocumentType.GIAOTRINH,
                    DocumentVersion.index_status == IndexStatus.INDEXED,
                )
                .distinct()
                .order_by(Document.title.asc())
            )
        ).all()
        materials: dict = {}
        for d in docs:
            materials.setdefault(d.course_id, []).append({"id": str(d.id), "title": d.title})

        due_rows = (
            await self.db.execute(
                select(
                    ReviewItem.course_id,
                    func.count().filter(ReviewItem.due_at.is_not(None), ReviewItem.due_at <= now).label("due"),
                    func.count().filter(ReviewItem.due_at.is_not(None)).label("learning"),
                )
                .where(ReviewItem.user_id == user_id, ReviewItem.course_id.in_(course_ids))
                .group_by(ReviewItem.course_id)
            )
        ).all()
        review = {r.course_id: (r.due, r.learning) for r in due_rows}

        # Điểm trung bình của vài lượt gần nhất mỗi môn: phản ánh hiện tại hơn trung bình toàn bộ.
        ranked = (
            select(
                QuizSession.course_id,
                QuizSession.score,
                func.row_number()
                .over(partition_by=QuizSession.course_id, order_by=QuizSession.submitted_at.desc())
                .label("rn"),
            )
            .where(
                QuizSession.user_id == user_id,
                QuizSession.status == QuizStatus.SUBMITTED,
                QuizSession.course_id.in_(course_ids),
            )
            .subquery()
        )
        score_rows = (
            await self.db.execute(
                select(ranked.c.course_id, func.count(), func.avg(ranked.c.score))
                .where(ranked.c.rn <= RECENT_QUIZZES)
                .group_by(ranked.c.course_id)
            )
        ).all()
        scores = {r[0]: (r[1], float(r[2]) if r[2] is not None else None) for r in score_rows}

        today = _today_vn()
        out = []
        for e in exams:
            exam_day = e.starts_at.astimezone(VN_TZ).date()
            due, learning = review.get(e.course_id, (0, 0))
            quiz_count, avg = scores.get(e.course_id, (0, None))
            mats = materials.get(e.course_id, [])
            out.append({
                "id": str(e.id),
                "course": {"id": str(e.course.id), "code": e.course.code, "name": e.course.name},
                "examDate": exam_day.isoformat(),
                "startsAt": e.starts_at,
                "durationMinutes": e.duration_minutes,
                "room": e.room,
                "building": e.building,
                "format": e.exam_format.value,
                "formatLabel": EXAM_FORMAT_LABEL.get(e.exam_format.value, e.exam_format.value),
                "allowedMaterials": e.allowed_materials,
                "daysLeft": (exam_day - today).days,
                "materials": mats,
                "progress": {
                    "quizCount": quiz_count,
                    "avgScore": round(avg, 1) if avg is not None else None,
                    "reviewDue": due,
                    "reviewLearning": learning,
                    "readiness": readiness(quiz_count, avg, due),
                },
                "plan": build_plan(today, exam_day, mats),
            })
        return {"today": today.isoformat(), "exams": out}
