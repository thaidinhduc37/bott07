"""Thống kê học tập cho giảng viên / cán bộ quản lý đào tạo.

Chỉ trả số liệu gộp, KHÔNG bao giờ trả tên, mã hay id học viên: mục đích là
biết phần nào của môn cần giảng lại, không phải theo dõi từng người. Một câu
chỉ vào danh sách "nhiều người sai" khi có ít nhất `MIN_LEARNERS` học viên khác
nhau sai — dưới ngưỡng đó, số liệu đủ nhỏ để đoán ra là ai.

Phạm vi:
  * LECTURER — chỉ các môn có `courses.lecturer_id` là mình.
  * ACADEMIC_MANAGER, ADMIN — mọi môn, và thêm danh sách câu hỏi hệ thống từ
    chối trả lời (dấu hiệu giáo trình/quy chế còn thiếu).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser
from app.models.academic import Course
from app.models.chat import ChatConversation, ChatMessage
from app.models.enums import MessageRole, RoleCode
from app.models.learning import QuizSession, QuizStatus, ReviewItem

MIN_LEARNERS = 2
WINDOW_DAYS = 30
LETTERS = "ABCD"


def _sees_all(user: AuthenticatedUser) -> bool:
    return RoleCode.ADMIN.value in user.roles or RoleCode.ACADEMIC_MANAGER.value in user.roles


class InsightsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _courses(self, user: AuthenticatedUser) -> list[Course]:
        stmt = select(Course).order_by(Course.code.asc())
        if not _sees_all(user):
            stmt = stmt.where(Course.lecturer_id == user.id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def overview(self, user: AuthenticatedUser) -> dict:
        courses = await self._courses(user)
        if not courses:
            return {"items": [], "windowDays": WINDOW_DAYS}
        ids = [c.id for c in courses]
        since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
        rows = (
            await self.db.execute(
                select(
                    QuizSession.course_id,
                    func.count().label("sessions"),
                    func.count(distinct(QuizSession.user_id)).label("learners"),
                    func.avg(QuizSession.score).label("avg"),
                )
                .where(
                    QuizSession.course_id.in_(ids),
                    QuizSession.status == QuizStatus.SUBMITTED,
                    QuizSession.submitted_at >= since,
                )
                .group_by(QuizSession.course_id)
            )
        ).all()
        stats = {r.course_id: r for r in rows}
        return {
            "windowDays": WINDOW_DAYS,
            "items": [
                {
                    "course": {"id": str(c.id), "code": c.code, "name": c.name},
                    "sessions": stats[c.id].sessions if c.id in stats else 0,
                    "learners": stats[c.id].learners if c.id in stats else 0,
                    "avgScore": round(float(stats[c.id].avg), 1) if c.id in stats and stats[c.id].avg is not None else None,
                }
                for c in courses
            ],
        }

    async def course_detail(self, user: AuthenticatedUser, course_id: str) -> dict:
        try:
            cid = uuid.UUID(course_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})
        course = next((c for c in await self._courses(user) if c.id == cid), None)
        if not course:
            # Môn của giảng viên khác: 404, không lộ là môn có tồn tại.
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})

        since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

        # Câu nhiều học viên sai: gộp sổ câu sai theo nội dung câu hỏi.
        hard_rows = (
            await self.db.execute(
                select(
                    ReviewItem.question_hash,
                    func.min(ReviewItem.question).label("question"),
                    func.min(ReviewItem.correct_index).label("correct_index"),
                    func.min(ReviewItem.source_file).label("source_file"),
                    func.min(ReviewItem.source_page).label("source_page"),
                    func.count(distinct(ReviewItem.user_id)).label("learners"),
                    func.sum(ReviewItem.times_wrong).label("wrong"),
                )
                .where(ReviewItem.course_id == cid)
                .group_by(ReviewItem.question_hash)
                .having(func.count(distinct(ReviewItem.user_id)) >= MIN_LEARNERS)
                .order_by(func.count(distinct(ReviewItem.user_id)).desc(), func.sum(ReviewItem.times_wrong).desc())
                .limit(15)
            )
        ).all()
        # Lấy phương án đúng từ một dòng bất kỳ của nhóm (cùng hash thì cùng nội dung).
        answers = {}
        if hard_rows:
            opt_rows = (
                await self.db.execute(
                    select(ReviewItem.question_hash, ReviewItem.options)
                    .where(ReviewItem.course_id == cid, ReviewItem.question_hash.in_([r.question_hash for r in hard_rows]))
                    .distinct(ReviewItem.question_hash)
                )
            ).all()
            answers = {r.question_hash: r.options for r in opt_rows}

        topic_rows = (
            await self.db.execute(
                select(
                    func.lower(func.trim(QuizSession.topic)).label("topic"),
                    func.count().label("sessions"),
                    func.count(distinct(QuizSession.user_id)).label("learners"),
                    func.avg(QuizSession.score).label("avg"),
                )
                .where(
                    QuizSession.course_id == cid,
                    QuizSession.status == QuizStatus.SUBMITTED,
                    QuizSession.topic.is_not(None),
                    QuizSession.submitted_at >= since,
                )
                .group_by(func.lower(func.trim(QuizSession.topic)))
                .order_by(func.count().desc())
                .limit(15)
            )
        ).all()

        return {
            "course": {"id": str(course.id), "code": course.code, "name": course.name},
            "windowDays": WINDOW_DAYS,
            "minLearners": MIN_LEARNERS,
            "hardQuestions": [
                {
                    "question": r.question,
                    "correctAnswer": (
                        f"{LETTERS[r.correct_index]}. {answers[r.question_hash][r.correct_index]}"
                        if r.question_hash in answers else None
                    ),
                    "sourceFile": r.source_file,
                    "sourcePage": r.source_page,
                    "learners": r.learners,
                    "timesWrong": int(r.wrong or 0),
                }
                for r in hard_rows
            ],
            "topics": [
                {
                    "topic": r.topic,
                    "sessions": r.sessions,
                    "learners": r.learners,
                    "avgScore": round(float(r.avg), 1) if r.avg is not None else None,
                }
                for r in topic_rows
            ],
        }

    async def unanswered(self, user: AuthenticatedUser, limit: int) -> dict:
        """Câu hỏi hệ thống từ chối trả lời trong `WINDOW_DAYS` ngày — chỉ nội dung câu hỏi."""
        if not _sees_all(user):
            raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền thực hiện thao tác này"})
        since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
        answer = ChatMessage.__table__.alias("answer")
        question = ChatMessage.__table__.alias("question")
        # Câu hỏi = tin USER gần nhất trước câu trả lời bị từ chối, trong cùng hội thoại.
        q_content = (
            select(question.c.content)
            .where(
                question.c.conversation_id == answer.c.conversation_id,
                question.c.role == MessageRole.USER.value,
                question.c.created_at <= answer.c.created_at,
            )
            .order_by(question.c.created_at.desc())
            .limit(1)
            .correlate(answer)
            .scalar_subquery()
        )
        rows = (
            await self.db.execute(
                select(q_content.label("question"), ChatConversation.mode, answer.c.confidence, answer.c.created_at)
                .select_from(answer.join(ChatConversation, ChatConversation.id == answer.c.conversation_id))
                .where(answer.c.abstained.is_(True), answer.c.created_at >= since)
                .order_by(answer.c.created_at.desc())
                .limit(limit)
            )
        ).all()
        return {
            "windowDays": WINDOW_DAYS,
            "items": [
                {
                    "question": r.question,
                    "mode": r.mode.value if hasattr(r.mode, "value") else r.mode,
                    "confidence": round(r.confidence, 3) if r.confidence is not None else None,
                    "createdAt": r.created_at,
                }
                for r in rows
                if r.question
            ],
        }
