"""Port of `chat/chat.service.ts`."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.academic import Course
from app.models.chat import ChatCitation, ChatConversation, ChatMessage
from app.models.documents import Document, DocumentVersion
from app.models.enums import ChatMode, DocumentType, IndexStatus, MessageRole
from app.schemas.chat import AskDto
from app.schemas.rag import QueryPayload, QueryResult
from app.services.rag_client import RagClientService, get_rag_client


def _rag_mode(mode: ChatMode) -> str:
    return "quyche" if mode == ChatMode.QUYCHE else "giaotrinh"


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class ChatService:
    def __init__(self, db, rag: RagClientService | None = None):
        self.db = db
        self.rag = rag or get_rag_client()

    # -------------------------------------------------------------------- ask

    async def ask(self, user_id: str, dto: AskDto) -> dict:
        # Ownership is verified BEFORE calling RAG. Without this step, changing
        # conversationId in the request body reads/writes into someone else's
        # conversation — the exact IDOR the reference guards against.
        conversation_id = dto.conversation_id
        if conversation_id:
            if not _is_valid_uuid(conversation_id):
                raise HTTPException(status_code=404, detail={"message": "Không tìm thấy hội thoại"})
            existing = (
                await self.db.execute(
                    select(ChatConversation.user_id, ChatConversation.mode).where(
                        ChatConversation.id == conversation_id
                    )
                )
            ).first()
            if not existing or str(existing.user_id) != str(user_id):
                # Deliberately 404, not 403 — anti-enumeration.
                raise HTTPException(status_code=404, detail={"message": "Không tìm thấy hội thoại"})
            if existing.mode != dto.mode:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "message": "Không thể đổi chế độ giữa chừng một hội thoại. Hãy bắt đầu hội thoại mới."
                    },
                )

        course_id: str | None = None
        if dto.course_id:
            if not _is_valid_uuid(dto.course_id):
                raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})
            course = (
                await self.db.execute(select(Course).where(Course.id == dto.course_id))
            ).scalar_one_or_none()
            if not course:
                raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})
            course_id = str(course.id)

        # Call RAG BEFORE writing anything to the DB. If rag-service dies
        # mid-request, we must not leave an orphaned conversation row with a
        # question and no answer.
        result = await self.rag.query(
            QueryPayload(question=dto.question, mode=_rag_mode(dto.mode), course_id=course_id)
        )

        if not conversation_id:
            conversation = ChatConversation(user_id=user_id, mode=dto.mode, title=dto.question[:120])
            self.db.add(conversation)
            await self.db.flush()
            conversation_id = str(conversation.id)
        else:
            await self.db.execute(
                ChatConversation.__table__.update()
                .where(ChatConversation.id == conversation_id)
                .values(updated_at=datetime.now(timezone.utc))
            )

        self.db.add(ChatMessage(conversation_id=conversation_id, role=MessageRole.USER, content=dto.question))

        assistant = ChatMessage(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=result.answer,
            abstained=result.abstained,
            confidence=result.confidence,
            threshold=result.threshold,
            grounded=result.grounded,
            route=result.route,
            rounds=result.rounds,
            latency_ms=result.latency_ms,
            trace=result.trace,
            retrieved_chunks=[c.model_dump(mode="json") for c in result.retrieved_chunks],
        )
        self.db.add(assistant)
        await self.db.flush()

        for c in result.citations:
            self.db.add(
                ChatCitation(
                    message_id=assistant.id,
                    marker=c.marker,
                    document_id=c.document_id,
                    document_title=c.document_title,
                    source_file=c.source_file,
                    page=c.page,
                    article_number=c.article_number,
                    rerank_score=c.rerank_score,
                    snippet=c.snippet,
                )
            )
        await self.db.flush()
        await self.db.refresh(assistant, attribute_names=["citations"])
        await self.db.commit()

        return {
            "conversationId": str(conversation_id),
            "message": self._present_message(assistant, result),
        }

    def _present_message(self, message: ChatMessage, result: QueryResult | None = None) -> dict:
        """Uniform shape for the frontend, used both by `ask` and history
        reload. NOTE: `abstainReason` is intentionally present here (sourced
        from the LIVE `result`, since the DB schema has no column for it) and
        intentionally ABSENT on history reload (`get_conversation`) — this
        asymmetry is in the reference and must not be "fixed"."""
        return {
            "id": str(message.id),
            "role": "ASSISTANT",
            "content": message.content,
            "abstained": message.abstained if message.abstained is not None else False,
            "abstainReason": result.abstain_reason if result is not None else None,
            "confidence": message.confidence,
            "threshold": message.threshold,
            "grounded": message.grounded,
            "route": message.route,
            "rounds": message.rounds,
            "latencyMs": message.latency_ms,
            "trace": message.trace,
            "citations": [self._present_citation(c) for c in message.citations],
            # The chunks the reader actually sees, so the UI can open them
            # side by side. Passed straight through in snake_case — NOT
            # remapped to camelCase, matching rag-service's raw JSON shape.
            "retrievedChunks": (
                [c.model_dump(mode="json") for c in result.retrieved_chunks] if result is not None else None
            ),
            "createdAt": message.created_at,
        }

    @staticmethod
    def _present_citation(c: ChatCitation) -> dict:
        return {
            "marker": c.marker,
            "documentId": str(c.document_id) if c.document_id else None,
            "documentTitle": c.document_title,
            "sourceFile": c.source_file,
            "page": c.page,
            "articleNumber": c.article_number,
            "rerankScore": c.rerank_score,
            "snippet": c.snippet,
        }

    # ------------------------------------------------------------------ lịch sử

    async def list_conversations(self, user_id: str, page: int = 1, page_size: int = 20) -> dict:
        total = (
            await self.db.execute(
                select(func.count()).select_from(ChatConversation).where(ChatConversation.user_id == user_id)
            )
        ).scalar_one()

        stmt = (
            select(ChatConversation)
            .options(selectinload(ChatConversation.messages))
            .where(ChatConversation.user_id == user_id)
            .order_by(ChatConversation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        items = [
            {
                "id": str(c.id),
                "title": c.title,
                "mode": c.mode,
                "createdAt": c.created_at,
                "updatedAt": c.updated_at,
                "messageCount": len(c.messages),
            }
            for c in rows
        ]
        return {"total": total, "page": page, "pageSize": page_size, "items": items}

    async def get_conversation(self, user_id: str, conversation_id: str) -> dict:
        stmt = (
            select(ChatConversation)
            .options(selectinload(ChatConversation.messages).selectinload(ChatMessage.citations))
            .where(ChatConversation.id == conversation_id)
        )
        conversation = (await self.db.execute(stmt)).scalar_one_or_none()

        # Same reasoning as documents: 404, not 403.
        if not conversation or str(conversation.user_id) != str(user_id):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy hội thoại"})

        messages = sorted(conversation.messages, key=lambda m: m.created_at)
        out_messages = []
        for m in messages:
            if m.role == MessageRole.USER:
                out_messages.append(
                    {"id": str(m.id), "role": "USER", "content": m.content, "createdAt": m.created_at}
                )
            else:
                # No `result` passed here -> abstainReason omitted, matching
                # the reference's intentional asymmetry on history reload.
                out_messages.append(self._present_message(m, result=None))

        return {
            "id": str(conversation.id),
            "title": conversation.title,
            "mode": conversation.mode,
            "createdAt": conversation.created_at,
            "messages": out_messages,
        }

    async def delete_conversation(self, user_id: str, conversation_id: str) -> dict:
        conversation = (
            await self.db.execute(select(ChatConversation).where(ChatConversation.id == conversation_id))
        ).scalar_one_or_none()
        if not conversation or str(conversation.user_id) != str(user_id):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy hội thoại"})
        await self.db.delete(conversation)
        await self.db.commit()
        return {"message": "Đã xóa hội thoại"}

    # -------------------------------------------------------------- readiness

    async def available_courses(self) -> dict:
        stmt = (
            select(Course.id, Course.code, Course.name)
            .join(Document, Document.course_id == Course.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(Document.document_type == DocumentType.GIAOTRINH, DocumentVersion.index_status == IndexStatus.INDEXED)
            .distinct()
            .order_by(Course.code.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        return {"items": [{"id": str(r.id), "code": r.code, "name": r.name} for r in rows]}

    async def modes_ready(self) -> dict:
        async def _count(doc_type: DocumentType) -> int:
            stmt = (
                select(func.count())
                .select_from(DocumentVersion)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(DocumentVersion.index_status == IndexStatus.INDEXED, Document.document_type == doc_type)
            )
            return (await self.db.execute(stmt)).scalar_one()

        quyche = await _count(DocumentType.QUYCHE)
        giaotrinh = await _count(DocumentType.GIAOTRINH)
        return {
            "QUYCHE": {"ready": quyche > 0, "documents": quyche},
            "GIAOTRINH": {"ready": giaotrinh > 0, "documents": giaotrinh},
        }

    # -------------------------------------------------------- admin dashboard

    async def get_admin_stats(self) -> dict:
        since_30d = datetime.now(timezone.utc) - timedelta(days=30)

        stmt = select(
            ChatMessage.created_at, ChatMessage.abstained, ChatMessage.confidence, ChatMessage.grounded
        ).where(ChatMessage.role == MessageRole.ASSISTANT, ChatMessage.created_at >= since_30d)
        messages_30d = (await self.db.execute(stmt)).all()

        by_mode_rows = (
            await self.db.execute(
                select(ChatConversation.mode, func.count()).group_by(ChatConversation.mode)
            )
        ).all()
        by_route_rows = (
            await self.db.execute(
                select(ChatMessage.route, func.count())
                .where(ChatMessage.role == MessageRole.ASSISTANT, ChatMessage.route.is_not(None))
                .group_by(ChatMessage.route)
            )
        ).all()

        by_day: dict[str, dict] = {}
        for m in messages_30d:
            day = m.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
            bucket = by_day.setdefault(
                day, {"total": 0, "abstained": 0, "groundedFailures": 0, "confidenceSum": 0.0, "confidenceCount": 0}
            )
            bucket["total"] += 1
            if m.abstained:
                bucket["abstained"] += 1
            if m.grounded is False:
                bucket["groundedFailures"] += 1
            if m.confidence is not None:
                bucket["confidenceSum"] += m.confidence
                bucket["confidenceCount"] += 1

        daily_trend = [
            {
                "day": day,
                "total": b["total"],
                "abstained": b["abstained"],
                "avgConfidence": (b["confidenceSum"] / b["confidenceCount"]) if b["confidenceCount"] else None,
                "groundedFailures": b["groundedFailures"],
            }
            for day, b in sorted(by_day.items())
        ]

        answered = [m for m in messages_30d if not m.abstained]
        grounded_failures_total = len([m for m in answered if m.grounded is False])

        return {
            "dailyTrend": daily_trend,
            "abstentionRate": (
                None if not messages_30d else len([m for m in messages_30d if m.abstained]) / len(messages_30d)
            ),
            "groundedFailureRate": None if not answered else grounded_failures_total / len(answered),
            "byMode": [{"mode": mode, "count": count} for mode, count in by_mode_rows],
            "byRoute": [{"route": route, "count": count} for route, count in by_route_rows],
        }
