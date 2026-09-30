"""Mounted at `/learning`. Ôn tập trắc nghiệm từ giáo trình + sổ câu sai.

Mọi route yêu cầu đăng nhập; dữ liệu luôn lọc theo người dùng của phiên
(xem `LearningService`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import AuthenticatedUser, get_current_user, get_db, rate_limit, require_roles
from app.models.enums import RoleCode
from app.schemas.learning import CreateQuizDto, CreateReviewDto, SubmitQuizDto
from app.schemas.notes import CreateNoteDto, NoteFromSourceDto, UpdateNoteDto
from app.services.exam_plan_service import ExamPlanService
from app.services.insights_service import InsightsService
from app.services.progress_service import ProgressService
from app.services.learning_service import LearningService
from app.services.notes_service import NotesService

router = APIRouter(prefix="/learning", tags=["learning"])


def _quiz_rate_limit():
    # Mỗi lần sinh đề là một lượt truy xuất + một lượt LLM, và nộp bài thêm một
    # lượt nhận xét — dùng chung hạn mức với hỏi đáp.
    return rate_limit("learning_quiz", get_settings().rate_limit_chat_per_min)


@router.post("/quiz", dependencies=[Depends(_quiz_rate_limit())])
async def create_quiz(
    dto: CreateQuizDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await LearningService(db).create_quiz(user.id, dto)


@router.post("/review")
async def create_review(
    dto: CreateReviewDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await LearningService(db).create_review(user.id, dto)


@router.get("/quiz")
async def list_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await LearningService(db).list_sessions(user.id, page, page_size)


@router.get("/quiz/{session_id}")
async def get_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await LearningService(db).get_session(user.id, session_id)


@router.post("/quiz/{session_id}/submit", dependencies=[Depends(_quiz_rate_limit())])
async def submit(
    session_id: str,
    dto: SubmitQuizDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await LearningService(db).submit(user.id, session_id, dto)


@router.get("/review-items")
async def review_overview(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await LearningService(db).review_overview(user.id)


@router.delete("/review-items/{item_id}")
async def delete_review_item(
    item_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await LearningService(db).delete_review_item(user.id, item_id)


# ------------------------------------------------------------ tiến trình


@router.get("/progress")
async def progress(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ProgressService(db).overview(user.id)


# ------------------------------------------------------------ kế hoạch ôn thi


@router.get("/exam-plan")
async def exam_plan(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ExamPlanService(db).plan(user.id)


# ------------------------------------------------------------ sổ tay


@router.get("/notes")
async def list_notes(
    q: str | None = Query(default=None, max_length=200),
    course_id: str | None = Query(default=None, alias="courseId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100, alias="pageSize"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await NotesService(db).list(user.id, q, course_id, page, page_size)


@router.post("/notes")
async def create_note(
    dto: CreateNoteDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await NotesService(db).create_manual(user.id, dto)


@router.post("/notes/from-chat")
async def note_from_chat(
    dto: NoteFromSourceDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await NotesService(db).from_chat(user.id, dto)


@router.post("/notes/from-quiz")
async def note_from_quiz(
    dto: NoteFromSourceDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await NotesService(db).from_quiz(user.id, dto)


@router.patch("/notes/{note_id}")
async def update_note(
    note_id: str,
    dto: UpdateNoteDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await NotesService(db).update(user.id, note_id, dto)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await NotesService(db).delete(user.id, note_id)


# ------------------------------------------------------------ thống kê cho giảng viên

_INSIGHT_ROLES = (RoleCode.LECTURER.value, RoleCode.ACADEMIC_MANAGER.value, RoleCode.ADMIN.value)


@router.get("/insights/courses")
async def insights_overview(
    user: AuthenticatedUser = Depends(require_roles(*_INSIGHT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).overview(user)


@router.get("/insights/courses/{course_id}")
async def insights_course(
    course_id: str,
    user: AuthenticatedUser = Depends(require_roles(*_INSIGHT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).course_detail(user, course_id)


@router.get("/insights/unanswered")
async def insights_unanswered(
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthenticatedUser = Depends(require_roles(RoleCode.ACADEMIC_MANAGER.value, RoleCode.ADMIN.value)),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).unanswered(user, limit)
