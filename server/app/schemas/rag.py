"""Internal payload/result shapes of the RAG pipeline.

Not exposed directly to the client (no `CamelModel` aliasing): `rag_client.py` builds and
parses them in snake_case. Do not import `CamelModel` here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RagDocumentType = Literal["quyche", "giaotrinh"]


# ------------------------------------------------------------------- /ingest

class IngestPayload(BaseModel):
    file_path: str
    document_id: str
    document_type: RagDocumentType
    title: str
    course_id: str | None = None


class IngestResult(BaseModel):
    document_id: str
    source: str
    collection: str
    pages: int
    chars: int
    chars_per_page: int
    likely_scanned: bool
    chunks: int
    contextualised: int
    points_upserted: int
    chunk_tokens: dict
    normalisation: dict
    seconds: float
    warnings: list[str] = Field(default_factory=list)


# -------------------------------------------------------------------- /query

class QueryPayload(BaseModel):
    """NOTE: deliberately has NO `tau` field — the reference NestJS type omits
    it so the API layer can never override the calibrated abstention
    threshold. Do not add it, even though rag-service's own QueryRequest
    schema accepts one."""

    question: str
    mode: RagDocumentType
    course_id: str | None = None
    top_k: int | None = None
    use_router: bool = True


class RagCitation(BaseModel):
    marker: int
    document_id: str | None = None
    document_title: str
    source_file: str
    page: int | None = None
    article_number: str | None = None
    article_range: str | None = None
    rerank_score: float | None = None
    snippet: str | None = None


class RagChunk(BaseModel):
    rank: int
    score: float
    source_file: str
    page: int | None = None
    article_number: str | None = None
    articles: list[str] = Field(default_factory=list)
    document_title: str
    text: str
    cited: bool


class QueryResult(BaseModel):
    answer: str
    citations: list[RagCitation]
    retrieved_chunks: list[RagChunk]
    latency_ms: int
    abstained: bool
    abstain_reason: str | None = None
    confidence: float
    threshold: float
    grounded: bool | None = None
    route: str
    rounds: int
    trace: list[str]
    llm_calls: int


# ----------------------------------------------------------------- /documents

class DeleteResult(BaseModel):
    document_id: str
    removed: dict[str, int]
    total: int


# ----------------------------------------------------------- learning aids

class SummarisePayload(BaseModel):
    topic: str
    course_id: str | None = None
    top_k: int | None = None


class SummariseResult(BaseModel):
    summary: str
    citations: list[RagCitation]
    retrieved_chunks: list[RagChunk]
    abstained: bool
    confidence: float
    threshold: float
    latency_ms: int


class QuizPayload(BaseModel):
    topic: str
    course_id: str | None = None
    n_questions: int | None = None
    top_k: int | None = None


class RagQuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    source_file: str | None = None
    source_page: int | None = None


class QuizResult(BaseModel):
    questions: list[RagQuizQuestion]
    abstained: bool
    abstain_reason: str | None = None
    confidence: float
    threshold: float
    latency_ms: int


class GradePayload(BaseModel):
    items: list[dict]
    score: float


class GradeResult(BaseModel):
    feedback: str
    latency_ms: int


# -------------------------------------------------------------------- /health

class RagHealth(BaseModel):
    status: str
    service: str
    version: str
    dependencies: dict
    collections: dict
    models: dict
    config: dict
    llm_usage: dict
