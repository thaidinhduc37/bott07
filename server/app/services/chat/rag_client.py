"""In-process facade over the RAG pipeline.

`chat_service`, `documents_service` and `learning_service` call `get_rag_client().query(...)`,
`.ingest(...)`, `.delete_document(...)`, `.health()` etc.; this class translates those calls
into direct calls on `app.pipeline.container.RagContainer` (models, Chroma store, retriever,
orchestrator, indexing service) and maps pipeline errors to HTTP errors.
"""

from __future__ import annotations

import json
import logging
import re
import time

from fastapi import HTTPException, status

from app.pipeline import blocking, prompts
from app.pipeline.llm import LlmUnavailable
from app.pipeline.orchestrator import build_context, cited_markers
from app.pipeline.container import RagContainer, get_rag_container, resolve_under_repo
from app.schemas.rag import (
    DeleteResult,
    GradePayload,
    GradeResult,
    IngestPayload,
    IngestResult,
    QueryPayload,
    QueryResult,
    QuizPayload,
    QuizResult,
    RagCitation,
    RagChunk,
    RagHealth,
    RagQuizQuestion,
    SummarisePayload,
    SummariseResult,
)

logger = logging.getLogger("rag_client")

_JSON_BLOCK_RE = re.compile(r"\[[\s\S]*\]")


def _service_unavailable(message: str, code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"message": message, "code": code})


def _chunks_payload(hits, cited: set[int]) -> list[RagChunk]:
    return [
        RagChunk(
            rank=i,
            score=round(h.score, 4),
            source_file=h.payload.get("source", ""),
            page=h.payload.get("page"),
            article_number=h.payload.get("article_number"),
            articles=h.payload.get("articles") or [],
            document_title=h.payload.get("title") or h.payload.get("source", ""),
            text=h.text,
            cited=i in cited,
        )
        for i, h in enumerate(hits, start=1)
    ]


class RagClientService:
    """In-process stand-in for the old HTTP `RagClientService`."""

    def __init__(self, container: RagContainer | None = None) -> None:
        self._c = container or get_rag_container()

    async def aclose(self) -> None:
        # Nothing to close — no HTTP client, no socket. Kept as a no-op so
        # `main.py`'s shutdown hook (`await get_rag_client().aclose()`) still
        # works unchanged.
        return None

    # ------------------------------------------------------------------ health

    async def health(self) -> RagHealth:
        c = self._c
        chroma_ok, chroma_detail = c.store.health()

        collections: dict = {}
        for doc_type in ("quyche", "giaotrinh"):
            name = c.settings.collection(doc_type)
            info = c.store.collection_info(name)
            collections[name] = {"dense_points": info["points"] if info else 0}

        data = {
            "status": "ok" if chroma_ok else "degraded",
            "service": "rag (in-process)",
            "version": "0.1.0",
            "dependencies": {
                "chroma": {
                    "ok": chroma_ok,
                    "detail": chroma_detail,
                    "url": f"http://{c.settings.chroma_host}:{c.settings.chroma_port}",
                },
                "llm": {
                    "ok": c.reader.available,
                    **c.reader.status(),
                    "detail": (
                        c.reader.circuit_reason
                        or ("khóa API đã đặt" if c.reader.available else "chưa cấu hình khóa API")
                    ),
                },
            },
            "collections": collections,
            "models": {
                "embedding": c.settings.embedding_model,
                "reranker": c.settings.reranker_model,
                **c.models.loaded,
            },
            "config": {
                "chunk_tokens": c.settings.chunk_tokens,
                "chunk_overlap": c.settings.chunk_overlap,
                "candidates_k": c.settings.candidates_k,
                "final_k": c.settings.final_k,
                "max_retrieval_rounds": c.settings.max_retrieval_rounds,
                "answer_threshold": c.settings.answer_threshold,
                "use_llm_context": c.settings.use_llm_context,
            },
            "llm_usage": c.reader.usage.snapshot(),
        }
        return RagHealth.model_validate(data)

    # ----------------------------------------------------------------- ingest

    async def ingest(self, payload: IngestPayload) -> IngestResult:
        c = self._c
        try:
            path = resolve_under_repo(payload.file_path)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}") from e

        try:
            report = await c.indexing.ingest(
                file_path=str(path),
                document_id=payload.document_id,
                document_type=payload.document_type,
                title=payload.title,
                course_id=payload.course_id,
            )
        except LlmUnavailable as e:
            raise _service_unavailable(str(e), "LLM_UNAVAILABLE") from e
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Nạp tài liệu thất bại: {payload.file_path}")
            raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}") from e

        return IngestResult(**report.__dict__)

    async def delete_document(self, document_id: str, document_type: str | None = None) -> DeleteResult:
        c = self._c
        result = await blocking.run(c.indexing.delete_document, document_id, document_type)
        return DeleteResult(**result)

    # ------------------------------------------------------------------ query

    async def query(self, payload: QueryPayload) -> QueryResult:
        c = self._c
        collection = c.settings.collection(payload.mode)

        if not c.store.collection_info(collection):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Chưa có tài liệu nào được nạp cho chế độ '{payload.mode}'. "
                    "Cán bộ quản lý cần nạp tài liệu trước khi hỏi đáp."
                ),
            )

        result = await c.orchestrator.answer(
            payload.question,
            collection,
            topics=c.corpus_topics(payload.mode),
            course_id=payload.course_id,
            top_k=payload.top_k,
            use_router=payload.use_router,
        )

        cited = {cit["marker"] for cit in result.citations}
        return QueryResult(
            answer=result.answer,
            citations=[RagCitation(**cit) for cit in result.citations],
            retrieved_chunks=_chunks_payload(result.hits, cited),
            latency_ms=result.latency_ms,
            abstained=result.abstained,
            abstain_reason=result.abstain_reason,
            confidence=round(result.confidence, 4),
            threshold=result.threshold,
            grounded=result.grounded,
            route=result.route,
            rounds=result.rounds,
            trace=result.trace,
            llm_calls=result.llm_calls,
        )

    # ------------------------------------------------------------- learning aids

    async def summarise(self, payload: SummarisePayload) -> SummariseResult:
        c = self._c
        t0 = time.time()
        collection = c.settings.collection("giaotrinh")
        if not c.store.collection_info(collection):
            raise HTTPException(status_code=409, detail="Chưa có giáo trình nào được nạp")

        hits = await blocking.run(
            c.retriever.retrieve, payload.topic, collection, top_k=payload.top_k or 8, course_id=payload.course_id
        )
        confidence = c.retriever.confidence(hits)
        tau = c.settings.answer_threshold

        if confidence < tau:
            return SummariseResult(
                summary=(
                    f"Tôi không tìm thấy nội dung đủ liên quan tới “{payload.topic}” trong giáo "
                    "trình đã nạp, nên tôi không tóm tắt để tránh đưa thông tin sai."
                ),
                citations=[],
                retrieved_chunks=_chunks_payload(hits, set()),
                abstained=True,
                confidence=round(confidence, 4),
                threshold=tau,
                latency_ms=int((time.time() - t0) * 1000),
            )

        try:
            text = await c.reader.chat(
                f"Ngữ cảnh:\n{build_context(hits)}\n\n---\nHãy tóm tắt nội dung về: {payload.topic}",
                system=prompts.SUMMARISE_SYSTEM,
                max_output_tokens=1024,
                tag="summarise",
            )
        except LlmUnavailable as e:
            raise _service_unavailable(str(e), "LLM_UNAVAILABLE") from e

        if text.strip().startswith("INSUFFICIENT_CONTEXT"):
            return SummariseResult(
                summary=(
                    f"Các đoạn tìm được về “{payload.topic}” quá rời rạc để tóm tắt thành một "
                    "nội dung mạch lạc."
                ),
                citations=[],
                retrieved_chunks=_chunks_payload(hits, set()),
                abstained=True,
                confidence=round(confidence, 4),
                threshold=tau,
                latency_ms=int((time.time() - t0) * 1000),
            )

        markers = cited_markers(text, len(hits))
        return SummariseResult(
            summary=text,
            citations=[RagCitation(**hits[m - 1].citation(m)) for m in markers],
            retrieved_chunks=_chunks_payload(hits, set(markers)),
            abstained=False,
            confidence=round(confidence, 4),
            threshold=tau,
            latency_ms=int((time.time() - t0) * 1000),
        )

    async def quiz(self, payload: QuizPayload) -> QuizResult:
        c = self._c
        t0 = time.time()
        collection = c.settings.collection("giaotrinh")
        if not c.store.collection_info(collection):
            raise HTTPException(status_code=409, detail="Chưa có giáo trình nào được nạp")

        n_questions = payload.n_questions or 5
        hits = await blocking.run(
            c.retriever.retrieve, payload.topic, collection, top_k=payload.top_k or 8, course_id=payload.course_id
        )
        confidence = c.retriever.confidence(hits)
        tau = c.settings.answer_threshold

        if confidence < tau:
            return QuizResult(
                questions=[],
                abstained=True,
                abstain_reason=(
                    f"Không tìm thấy nội dung đủ liên quan tới “{payload.topic}” trong giáo trình "
                    f"(độ tin cậy {confidence:.3f} dưới ngưỡng {tau:.3f}). Không sinh câu hỏi "
                    "để tránh tạo ra kiến thức sai."
                ),
                confidence=round(confidence, 4),
                threshold=tau,
                latency_ms=int((time.time() - t0) * 1000),
            )

        try:
            raw = await c.reader.chat(
                f"Ngữ cảnh:\n{build_context(hits)}\n\n---\n"
                f"Soạn {n_questions} câu hỏi trắc nghiệm về: {payload.topic}",
                system=prompts.QUIZ_SYSTEM.format(n=n_questions),
                max_output_tokens=2048,
                tag="quiz",
            )
        except LlmUnavailable as e:
            raise _service_unavailable(str(e), "LLM_UNAVAILABLE") from e

        match = _JSON_BLOCK_RE.search(raw)
        if not match:
            raise HTTPException(
                status_code=502,
                detail="Mô hình không trả về JSON hợp lệ cho bộ câu hỏi. Thử lại hoặc đổi chủ đề.",
            )
        try:
            items = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=502, detail=f"JSON câu hỏi không phân tích được: {e}") from e

        questions: list[RagQuizQuestion] = []
        for item in items:
            try:
                options = [str(o) for o in item["options"]]
                correct = int(item["correct_index"])
                if len(options) != 4 or not (0 <= correct < 4):
                    continue
                passage_no = item.get("passage")
                source_file = source_page = None
                if isinstance(passage_no, int) and 1 <= passage_no <= len(hits):
                    p = hits[passage_no - 1].payload
                    source_file = p.get("source")
                    source_page = p.get("page")
                questions.append(
                    RagQuizQuestion(
                        question=str(item["question"]),
                        options=options,
                        correct_index=correct,
                        explanation=str(item.get("explanation", "")),
                        source_file=source_file,
                        source_page=source_page,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue

        if not questions:
            return QuizResult(
                questions=[],
                abstained=True,
                abstain_reason="Không sinh được câu hỏi nào bám sát ngữ cảnh truy xuất.",
                confidence=round(confidence, 4),
                threshold=tau,
                latency_ms=int((time.time() - t0) * 1000),
            )

        return QuizResult(
            questions=questions,
            abstained=False,
            confidence=round(confidence, 4),
            threshold=tau,
            latency_ms=int((time.time() - t0) * 1000),
        )

    async def grade_feedback(self, payload: GradePayload) -> GradeResult:
        c = self._c
        t0 = time.time()
        lines = []
        for i, item in enumerate(payload.items, start=1):
            verdict = "đúng" if item.get("chosen") == item.get("correct") else "SAI"
            lines.append(
                f"{i}. {item.get('question', '')}\n"
                f"   Học viên chọn: {item.get('chosen_text', item.get('chosen'))} ({verdict})\n"
                f"   Đáp án: {item.get('correct_text', item.get('correct'))}\n"
                f"   Giải thích: {item.get('explanation', '')}"
            )
        try:
            feedback = await c.reader.chat(
                f"Điểm: {payload.score:.1f}/10\n\n" + "\n\n".join(lines),
                system=prompts.FEEDBACK_SYSTEM,
                max_output_tokens=400,
                tag="feedback",
            )
        except LlmUnavailable as e:
            raise _service_unavailable(str(e), "LLM_UNAVAILABLE") from e

        return GradeResult(feedback=feedback, latency_ms=int((time.time() - t0) * 1000))


_rag_client: RagClientService | None = None


def get_rag_client() -> RagClientService:
    """Module-level singleton — one instance wraps the one `RagContainer`."""
    global _rag_client
    if _rag_client is None:
        _rag_client = RagClientService()
    return _rag_client
