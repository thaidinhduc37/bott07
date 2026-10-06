"""Sổ tay học tập — lưu câu trả lời hỏi đáp, câu trắc nghiệm, ghi chú tự viết.

Quyền sở hữu luôn kiểm tra qua chuỗi khóa ngoại tới `user_id` của phiên (tin
nhắn -> hội thoại -> người dùng; câu hỏi -> lượt ôn -> người dùng). Id không
thuộc về mình trả 404, không phải 403.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.academic import Course
from app.models.chat import ChatConversation, ChatMessage
from app.models.enums import MessageRole
from app.models.learning import QuizQuestion, QuizSession, QuizStatus
from app.models.notes import NOTE_SOURCE_CHAT, NOTE_SOURCE_MANUAL, NOTE_SOURCE_QUIZ, StudyNote
from app.schemas.notes import CreateNoteDto, NoteFromSourceDto, UpdateNoteDto

LETTERS = "ABCD"


def _uuid_or_404(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail={"message": f"Không tìm thấy {what}"})


class NotesService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _present(self, notes: list[StudyNote]) -> list[dict]:
        ids = {n.course_id for n in notes if n.course_id}
        courses = {}
        if ids:
            rows = (await self.db.execute(select(Course.id, Course.code, Course.name).where(Course.id.in_(ids)))).all()
            courses = {r.id: {"id": str(r.id), "code": r.code, "name": r.name} for r in rows}
        return [
            {
                "id": str(n.id),
                "sourceType": n.source_type,
                "sourceId": str(n.source_id) if n.source_id else None,
                "course": courses.get(n.course_id),
                "title": n.title,
                "content": n.content,
                "citations": n.citations,
                "note": n.note,
                "pinned": n.pinned,
                "createdAt": n.created_at,
                "updatedAt": n.updated_at,
            }
            for n in notes
        ]

    async def _course_id(self, course_id: str | None) -> uuid.UUID | None:
        if not course_id:
            return None
        cid = _uuid_or_404(course_id, "môn học")
        if not (await self.db.execute(select(Course.id).where(Course.id == cid))).first():
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})
        return cid

    async def _existing(self, user_id: str, source_type: str, source_id: uuid.UUID) -> StudyNote | None:
        return (
            await self.db.execute(
                select(StudyNote).where(
                    StudyNote.user_id == user_id,
                    StudyNote.source_type == source_type,
                    StudyNote.source_id == source_id,
                )
            )
        ).scalar_one_or_none()

    async def _save(self, note: StudyNote) -> dict:
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        return (await self._present([note]))[0]

    # ------------------------------------------------------------ đọc

    async def list(self, user_id: str, q: str | None, course_id: str | None, page: int, page_size: int) -> dict:
        cond = [StudyNote.user_id == user_id]
        if course_id:
            cond.append(StudyNote.course_id == _uuid_or_404(course_id, "môn học"))
        if q and q.strip():
            like = f"%{q.strip()}%"
            cond.append(or_(StudyNote.title.ilike(like), StudyNote.content.ilike(like), StudyNote.note.ilike(like)))
        rows = (
            await self.db.execute(
                select(StudyNote)
                .where(*cond)
                .order_by(StudyNote.pinned.desc(), StudyNote.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        total = (await self.db.execute(select(func.count()).select_from(StudyNote).where(*cond))).scalar_one()
        return {"items": await self._present(list(rows)), "total": total}

    # ------------------------------------------------------------ tạo

    async def from_chat(self, user_id: str, dto: NoteFromSourceDto) -> dict:
        message_id = _uuid_or_404(dto.source_id, "câu trả lời")
        existing = await self._existing(user_id, NOTE_SOURCE_CHAT, message_id)
        if existing:
            return (await self._present([existing]))[0]

        row = (
            await self.db.execute(
                select(ChatMessage, ChatConversation)
                .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
                .options(selectinload(ChatMessage.citations))
                .where(ChatMessage.id == message_id, ChatConversation.user_id == user_id)
            )
        ).first()
        if not row or row.ChatMessage.role != MessageRole.ASSISTANT:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy câu trả lời"})
        message = row.ChatMessage
        if message.abstained:
            # Câu từ chối trả lời không có kiến thức gì để lưu.
            raise HTTPException(status_code=409, detail={"message": "Câu trả lời này là từ chối, không lưu được"})

        # Câu hỏi đứng ngay trước câu trả lời làm tiêu đề ghi chú.
        question = (
            await self.db.execute(
                select(ChatMessage.content)
                .where(
                    ChatMessage.conversation_id == message.conversation_id,
                    ChatMessage.role == MessageRole.USER,
                    ChatMessage.created_at <= message.created_at,
                )
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        citations = [
            {
                "marker": c.marker,
                "documentTitle": c.document_title,
                "sourceFile": c.source_file,
                "page": c.page,
                "articleNumber": c.article_number,
                "snippet": c.snippet,
            }
            for c in sorted(message.citations, key=lambda c: c.marker)
        ]
        course_id = await self._course_id(dto.course_id)
        return await self._save(
            StudyNote(
                user_id=user_id,
                course_id=course_id,
                source_type=NOTE_SOURCE_CHAT,
                source_id=message.id,
                title=(question or row.ChatConversation.title or "Câu trả lời đã lưu")[:300],
                content=message.content,
                citations=citations,
                note=dto.note,
            )
        )

    async def from_quiz(self, user_id: str, dto: NoteFromSourceDto) -> dict:
        question_id = _uuid_or_404(dto.source_id, "câu hỏi")
        existing = await self._existing(user_id, NOTE_SOURCE_QUIZ, question_id)
        if existing:
            return (await self._present([existing]))[0]

        row = (
            await self.db.execute(
                select(QuizQuestion, QuizSession)
                .join(QuizSession, QuizSession.id == QuizQuestion.session_id)
                .where(QuizQuestion.id == question_id, QuizSession.user_id == user_id)
            )
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy câu hỏi"})
        q, session = row.QuizQuestion, row.QuizSession
        if session.status != QuizStatus.SUBMITTED:
            # Chưa nộp mà lưu được thì lộ đáp án qua sổ tay.
            raise HTTPException(status_code=409, detail={"message": "Nộp bài xong mới lưu được câu hỏi"})

        content = (
            f"Đáp án: {LETTERS[q.correct_index]}. {q.options[q.correct_index]}\n\n{q.explanation}"
        )
        citations = (
            [{"marker": 1, "documentTitle": q.source_file, "sourceFile": q.source_file, "page": q.source_page,
              "articleNumber": None, "snippet": None}]
            if q.source_file
            else []
        )
        return await self._save(
            StudyNote(
                user_id=user_id,
                course_id=session.course_id,
                source_type=NOTE_SOURCE_QUIZ,
                source_id=q.id,
                title=q.question[:300],
                content=content,
                citations=citations,
                note=dto.note,
            )
        )

    async def create_manual(self, user_id: str, dto: CreateNoteDto) -> dict:
        course_id = await self._course_id(dto.course_id)
        return await self._save(
            StudyNote(
                user_id=user_id,
                course_id=course_id,
                source_type=NOTE_SOURCE_MANUAL,
                title=dto.title,
                content=dto.content,
                citations=[],
            )
        )

    # ------------------------------------------------------------ sửa / xóa

    async def _owned(self, user_id: str, note_id: str) -> StudyNote:
        nid = _uuid_or_404(note_id, "ghi chú")
        note = (
            await self.db.execute(select(StudyNote).where(StudyNote.id == nid, StudyNote.user_id == user_id))
        ).scalar_one_or_none()
        if not note:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy ghi chú"})
        return note

    async def update(self, user_id: str, note_id: str, dto: UpdateNoteDto) -> dict:
        note = await self._owned(user_id, note_id)
        data = dto.model_dump(exclude_unset=True)
        if "note" in data:
            note.note = data["note"] or None
        if "pinned" in data and data["pinned"] is not None:
            note.pinned = data["pinned"]
        if data.get("title"):
            note.title = data["title"]
        # Chỉ ghi chú tự viết mới sửa được nội dung — nội dung chép từ nguồn phải khớp nguồn.
        if data.get("content") is not None:
            if note.source_type != NOTE_SOURCE_MANUAL:
                raise HTTPException(
                    status_code=409, detail={"message": "Không sửa được nội dung chép từ nguồn, hãy dùng phần ghi chú riêng"}
                )
            note.content = data["content"]
        return await self._save(note)

    async def delete(self, user_id: str, note_id: str) -> dict:
        note = await self._owned(user_id, note_id)
        await self.db.delete(note)
        await self.db.commit()
        return {"message": "Đã xóa ghi chú"}
