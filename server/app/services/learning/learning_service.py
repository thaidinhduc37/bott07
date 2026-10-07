"""Ôn tập từ giáo trình: sinh đề, chấm bài, sổ câu sai (hộp Leitner).

Câu hỏi mới đến từ `RagClientService.quiz()`, tức là đi qua cùng cổng τ với
hỏi đáp: chủ đề không đủ căn cứ trong giáo trình thì trả `abstained` và KHÔNG
tạo lượt làm bài nào. Không sinh câu hỏi bằng kiến thức ngoài giáo trình.

Mọi truy vấn đều lọc theo `user_id` của phiên; id của người khác trả 404
(không phải 403) — cùng cách chống dò id như hội thoại.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.academic import Course
from app.models.learning import QuizQuestion, QuizSession, QuizStatus, ReviewItem
from app.schemas.learning import CreateQuizDto, CreateReviewDto, SubmitQuizDto
from app.schemas.rag import GradePayload, QuizPayload
from app.services.chat.rag_client import RagClientService, get_rag_client
from app.services.learning.answers import correct_of, correct_text, selected_of
from app.services.learning.question_bank_service import QuestionBankService

logger = logging.getLogger("learning")

# Hộp -> số ngày đến lần ôn tiếp theo. Đúng ở hộp cuối thì coi là đã thuộc.
LEITNER_DAYS = {1: 1, 2: 3, 3: 7, 4: 14}
LAST_BOX = max(LEITNER_DAYS)
# Số câu sai đến hạn trộn vào một đề mới.
REVIEW_MIX = 3


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, TypeError):
        return False
    return True


def _question_hash(question: str, options: list[str]) -> str:
    raw = question.strip().lower() + "\n" + "\n".join(o.strip().lower() for o in options)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _not_found(what: str = "lượt ôn tập") -> HTTPException:
    return HTTPException(status_code=404, detail={"message": f"Không tìm thấy {what}"})


class LearningService:
    def __init__(self, db: AsyncSession, rag: RagClientService | None = None) -> None:
        self.db = db
        self.rag = rag or get_rag_client()

    # ------------------------------------------------------------ helpers

    async def _resolve_course(self, course_id: str | None) -> Course | None:
        if not course_id:
            return None
        if not _is_valid_uuid(course_id):
            raise _not_found("môn học")
        course = (await self.db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
        if not course:
            raise _not_found("môn học")
        return course

    async def _due_items(self, user_id: str, course_id: str | None, limit: int) -> list[ReviewItem]:
        stmt = select(ReviewItem).where(
            ReviewItem.user_id == user_id,
            ReviewItem.due_at.is_not(None),
            ReviewItem.due_at <= _now(),
        )
        if course_id:
            stmt = stmt.where(ReviewItem.course_id == course_id)
        stmt = stmt.order_by(ReviewItem.box.asc(), ReviewItem.due_at.asc()).limit(limit)
        return list((await self.db.execute(stmt)).scalars().all())

    async def _load_session(self, user_id: str, session_id: str, *, for_update: bool = False) -> QuizSession:
        if not _is_valid_uuid(session_id):
            raise _not_found()
        stmt = (
            select(QuizSession)
            .where(QuizSession.id == session_id, QuizSession.user_id == user_id)
            .options(selectinload(QuizSession.questions))
        )
        if for_update:
            # Hai lần nộp đồng thời không được chấm (và cộng hộp Leitner) hai lần.
            stmt = stmt.with_for_update(of=QuizSession)
        session = (await self.db.execute(stmt)).scalar_one_or_none()
        if not session:
            raise _not_found()
        return session

    async def _course_refs(self, ids: set) -> dict:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = (await self.db.execute(select(Course.id, Course.code, Course.name).where(Course.id.in_(ids)))).all()
        return {r.id: {"id": str(r.id), "code": r.code, "name": r.name} for r in rows}

    async def _present(self, session: QuizSession) -> dict:
        reveal = session.status == QuizStatus.SUBMITTED
        courses = await self._course_refs({session.course_id})
        questions = []
        for q in session.questions:
            item = {
                "id": str(q.id),
                "ordinal": q.ordinal,
                "question": q.question,
                "options": q.options,
                # Câu nhiều đáp án đúng hiện ô tick; KHÔNG nói trước có mấy đáp án đúng (như Moodle).
                "multi": bool(q.correct_set),
                "fromReview": q.review_item_id is not None,
            }
            # Chưa nộp thì không lộ đáp án ra client.
            if reveal:
                item.update(
                    correctIndex=q.correct_index,
                    correctIndexes=correct_of(q),
                    explanation=q.explanation,
                    sourceFile=q.source_file,
                    sourcePage=q.source_page,
                    selectedIndex=q.selected_index,
                    selectedIndexes=selected_of(q),
                    isCorrect=q.is_correct,
                )
            questions.append(item)
        return {
            "id": str(session.id),
            "topic": session.topic,
            "course": courses.get(session.course_id),
            "status": session.status.value,
            "score": session.score,
            "feedback": session.feedback,
            "confidence": session.confidence,
            "submittedAt": session.submitted_at,
            "createdAt": session.created_at,
            "questions": questions,
        }

    # ------------------------------------------------------------ tạo đề

    async def _create_bank_quiz(self, user_id: str, dto: CreateQuizDto, course: Course) -> dict:
        """Đề rút ngẫu nhiên từ ngân hàng câu hỏi của giảng viên: không gọi AI nên không cần ngưỡng τ."""
        picked = await QuestionBankService(self.db).draw(course.id, dto.n_questions)
        if not picked:
            raise HTTPException(
                status_code=400, detail={"message": "Môn này chưa có ngân hàng câu hỏi", "code": "BANK_EMPTY"}
            )
        session = QuizSession(
            user_id=user_id, course_id=course.id, status=QuizStatus.IN_PROGRESS,
            topic=dto.topic or f"Ngân hàng câu hỏi {course.code}",
        )
        ordinal = 1
        for q in picked:
            session.questions.append(
                QuizQuestion(
                    ordinal=ordinal, question=q.question, options=q.options, correct_index=q.correct_index,
                    correct_set=q.correct_set, explanation=q.explanation,
                    source_file="Ngân hàng câu hỏi" + (f" · {q.chapter}" if q.chapter else ""),
                )
            )
            ordinal += 1
        if dto.include_review:
            fresh = {q.question_hash for q in picked}
            for item in await self._due_items(user_id, str(course.id), REVIEW_MIX):
                if item.question_hash in fresh:
                    continue
                session.questions.append(self._question_from_review(item, ordinal))
                ordinal += 1
        self.db.add(session)
        await self.db.commit()
        return {"abstained": False, "session": await self._present(await self._load_session(user_id, str(session.id)))}

    async def create_quiz(self, user_id: str, dto: CreateQuizDto) -> dict:
        course = await self._resolve_course(dto.course_id)
        course_id = str(course.id) if course else None
        if dto.source == "bank":
            if course is None:
                raise HTTPException(status_code=400, detail={"message": "Chọn môn học để ôn từ ngân hàng câu hỏi"})
            return await self._create_bank_quiz(user_id, dto, course)

        # Gọi RAG TRƯỚC khi ghi DB: LLM lỗi thì không để lại lượt làm bài rỗng.
        result = await self.rag.quiz(
            QuizPayload(topic=dto.topic, course_id=course_id, n_questions=dto.n_questions)
        )
        if result.abstained:
            return {
                "abstained": True,
                "reason": result.abstain_reason,
                "confidence": result.confidence,
                "threshold": result.threshold,
            }

        session = QuizSession(
            user_id=user_id,
            course_id=course.id if course else None,
            topic=dto.topic,
            status=QuizStatus.IN_PROGRESS,
            confidence=result.confidence,
        )
        ordinal = 1
        for q in result.questions:
            session.questions.append(
                QuizQuestion(
                    ordinal=ordinal,
                    question=q.question,
                    options=q.options,
                    correct_index=q.correct_index,
                    explanation=q.explanation,
                    source_file=q.source_file,
                    source_page=q.source_page,
                )
            )
            ordinal += 1

        if dto.include_review:
            fresh = {_question_hash(q.question, q.options) for q in result.questions}
            for item in await self._due_items(user_id, course_id, REVIEW_MIX):
                if item.question_hash in fresh:
                    continue
                session.questions.append(self._question_from_review(item, ordinal))
                ordinal += 1

        self.db.add(session)
        await self.db.commit()
        return {"abstained": False, "session": await self._present(await self._load_session(user_id, str(session.id)))}

    @staticmethod
    def _question_from_review(item: ReviewItem, ordinal: int) -> QuizQuestion:
        return QuizQuestion(
            ordinal=ordinal,
            question=item.question,
            options=item.options,
            correct_index=item.correct_index,
            correct_set=item.correct_set,
            explanation=item.explanation,
            source_file=item.source_file,
            source_page=item.source_page,
            review_item_id=item.id,
        )

    async def create_review(self, user_id: str, dto: CreateReviewDto) -> dict:
        """Lượt ôn chỉ gồm câu sai đã đến hạn — không gọi LLM."""
        course = await self._resolve_course(dto.course_id)
        items = await self._due_items(user_id, str(course.id) if course else None, dto.limit)
        if not items:
            raise HTTPException(
                status_code=409,
                detail={"message": "Chưa có câu nào đến hạn ôn lại", "code": "NOTHING_DUE"},
            )
        session = QuizSession(
            user_id=user_id,
            course_id=course.id if course else None,
            topic=None,
            status=QuizStatus.IN_PROGRESS,
        )
        for i, item in enumerate(items, start=1):
            session.questions.append(self._question_from_review(item, i))
        self.db.add(session)
        await self.db.commit()
        return await self._present(await self._load_session(user_id, str(session.id)))

    # ------------------------------------------------------------ nộp bài

    async def submit(self, user_id: str, session_id: str, dto: SubmitQuizDto) -> dict:
        session = await self._load_session(user_id, session_id, for_update=True)
        if session.status != QuizStatus.IN_PROGRESS:
            raise HTTPException(status_code=409, detail={"message": "Lượt ôn tập này đã nộp rồi"})

        chosen = {a.question_id: a for a in dto.answers}
        now = _now()
        correct = 0
        for q in session.questions:
            a = chosen.get(str(q.id))
            if q.correct_set:
                # Nhiều đáp án đúng: đúng khi tick ĐÚNG và ĐỦ các đáp án (không tính điểm một phần).
                picked = sorted({i for i in (a.selected_indexes or []) if 0 <= i < len(q.options)}) if a else []
                q.selected_index = None
                q.selected_set = picked or None
                q.is_correct = bool(picked) and picked == sorted(q.correct_set)
            else:
                selected = a.selected_index if a else None
                q.selected_index = selected
                q.is_correct = selected is not None and selected == q.correct_index
            correct += int(q.is_correct)
            await self._update_review(user_id, session.course_id, q, now)

        total = len(session.questions)
        session.score = round(correct / total * 10, 1) if total else 0.0
        session.status = QuizStatus.SUBMITTED
        session.submitted_at = now
        await self.db.commit()

        # Nhận xét là phần phụ: LLM hết hạn mức thì vẫn trả kết quả chấm.
        try:
            grade = await self.rag.grade_feedback(
                GradePayload(
                    score=session.score,
                    items=[
                        {
                            "question": q.question,
                            "chosen": q.selected_index,
                            "correct": q.correct_index,
                            "chosen_text": correct_text(q.options, selected_of(q)) if selected_of(q) else "(bỏ trống)",
                            "correct_text": correct_text(q.options, correct_of(q)),
                            "explanation": q.explanation,
                        }
                        for q in session.questions
                    ],
                )
            )
            session.feedback = grade.feedback.strip() or None
            await self.db.commit()
        except HTTPException as e:
            logger.warning("Không sinh được nhận xét bài làm: %s", e.detail)

        return await self._present(await self._load_session(user_id, session_id))

    async def _update_review(self, user_id: str, course_id, q: QuizQuestion, now: datetime) -> None:
        if q.review_item_id is not None:
            item = await self.db.get(ReviewItem, q.review_item_id)
        else:
            item = (
                await self.db.execute(
                    select(ReviewItem).where(
                        ReviewItem.user_id == user_id,
                        ReviewItem.question_hash == _question_hash(q.question, q.options),
                    )
                )
            ).scalar_one_or_none()

        if q.is_correct:
            # Câu mới làm đúng thì không cần ghi sổ. Chỉ câu đang ôn mới lên hộp.
            if item is None or item.due_at is None:
                return
            item.times_right += 1
            item.box += 1
            item.due_at = None if item.box > LAST_BOX else now + timedelta(days=LEITNER_DAYS[item.box])
            item.last_reviewed_at = now
            return

        if item is None:
            item = ReviewItem(
                user_id=user_id,
                course_id=course_id,
                question_hash=_question_hash(q.question, q.options),
                question=q.question,
                options=q.options,
                correct_index=q.correct_index,
                correct_set=q.correct_set,
                explanation=q.explanation,
                source_file=q.source_file,
                source_page=q.source_page,
                times_wrong=0,
                times_right=0,
            )
            self.db.add(item)
            await self.db.flush()
            q.review_item_id = item.id
        item.times_wrong += 1
        item.box = 1
        item.due_at = now + timedelta(days=LEITNER_DAYS[1])
        item.last_reviewed_at = now

    # ------------------------------------------------------------ đọc

    async def get_session(self, user_id: str, session_id: str) -> dict:
        return await self._present(await self._load_session(user_id, session_id))

    async def list_sessions(self, user_id: str, page: int, page_size: int) -> dict:
        n_questions = (
            select(func.count())
            .select_from(QuizQuestion)
            .where(QuizQuestion.session_id == QuizSession.id)
            .correlate(QuizSession)
            .scalar_subquery()
        )
        stmt = (
            select(QuizSession, n_questions.label("n_questions"))
            .where(QuizSession.user_id == user_id)
            .order_by(QuizSession.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()
        total = (
            await self.db.execute(select(func.count()).select_from(QuizSession).where(QuizSession.user_id == user_id))
        ).scalar_one()
        courses = await self._course_refs({r.QuizSession.course_id for r in rows})
        return {
            "items": [
                {
                    "id": str(s.id),
                    "topic": s.topic,
                    "course": courses.get(s.course_id),
                    "status": s.status.value,
                    "score": s.score,
                    "questionCount": n,
                    "submittedAt": s.submitted_at,
                    "createdAt": s.created_at,
                }
                for s, n in rows
            ],
            "total": total,
        }

    async def review_overview(self, user_id: str) -> dict:
        items = (
            await self.db.execute(
                select(ReviewItem)
                .where(ReviewItem.user_id == user_id)
                .order_by(ReviewItem.due_at.asc().nulls_last(), ReviewItem.updated_at.desc())
                .limit(200)
            )
        ).scalars().all()
        now = _now()
        courses = await self._course_refs({i.course_id for i in items})
        stats = (
            await self.db.execute(
                select(
                    func.count().filter(ReviewItem.due_at.is_not(None), ReviewItem.due_at <= now).label("due"),
                    func.count().filter(ReviewItem.due_at.is_not(None)).label("learning"),
                    func.count().filter(ReviewItem.due_at.is_(None)).label("mastered"),
                ).where(ReviewItem.user_id == user_id)
            )
        ).one()
        return {
            "due": stats.due,
            "learning": stats.learning,
            "mastered": stats.mastered,
            "items": [
                {
                    "id": str(i.id),
                    "course": courses.get(i.course_id),
                    "question": i.question,
                    "options": i.options,
                    "correctIndex": i.correct_index,
                    "correctIndexes": correct_of(i),
                    "explanation": i.explanation,
                    "sourceFile": i.source_file,
                    "sourcePage": i.source_page,
                    "box": i.box,
                    "dueAt": i.due_at,
                    "isDue": i.due_at is not None and i.due_at <= now,
                    "mastered": i.due_at is None,
                    "timesWrong": i.times_wrong,
                    "timesRight": i.times_right,
                }
                for i in items
            ],
        }

    async def delete_review_item(self, user_id: str, item_id: str) -> dict:
        if not _is_valid_uuid(item_id):
            raise _not_found("câu hỏi")
        item = (
            await self.db.execute(select(ReviewItem).where(ReviewItem.id == item_id, ReviewItem.user_id == user_id))
        ).scalar_one_or_none()
        if not item:
            raise _not_found("câu hỏi")
        await self.db.delete(item)
        await self.db.commit()
        return {"message": "Đã xóa khỏi sổ câu sai"}
