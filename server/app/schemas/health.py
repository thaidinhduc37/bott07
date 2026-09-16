from __future__ import annotations

from app.schemas.base import CamelReadModel


class HealthOut(CamelReadModel):
    status: str
    service: str


class PostgresDepOut(CamelReadModel):
    ok: bool
    latency_ms: int | None = None


class RagServiceDepOut(CamelReadModel):
    ok: bool
    detail: str
    url: str
    collections: dict = {}


class LlmDepOut(CamelReadModel):
    ok: bool
    detail: str | None = None
    provider: str | None = None


class DependenciesOut(CamelReadModel):
    postgres: PostgresDepOut
    rag_service: RagServiceDepOut
    llm: LlmDepOut | None = None


class CountersOut(CamelReadModel):
    users: int
    indexed_document_versions: int
    submissions: int


class HealthDetailOut(CamelReadModel):
    status: str
    dependencies: DependenciesOut
    counters: CountersOut
    uptime_seconds: int
    memory_mb: int
