"""App configuration — merged from `server/api-py/app/config.py` (web/DB layer)
and `server/rag-service/app/config.py` (RAG pipeline layer).

This is the unified `server/app/` — api-py and rag-service are no longer two
processes talking over HTTP; they are one FastAPI app (`server/main.py`) with
one `Settings` object. All parameter names are kept identical to their
original service so the ported pipeline/router code needs no renames.

Reads `server/.env` — the single env file for this app. Docker Compose (used
only to run Postgres/Chroma) reads the same file via `--env-file server/.env`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# server/app/config.py -> parents[0]=app, [1]=server, [2]=repo root
_parents = Path(__file__).resolve().parents
REPO_ROOT = _parents[2] if len(_parents) > 2 else _parents[-1]
SERVICE_ROOT = _parents[1]  # server/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(SERVICE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --------------------------------------------------------------- general
    node_env: str = "development"
    tz: str = "Asia/Ho_Chi_Minh"

    # -------------------------------------------------------------- postgres
    database_url: str = (
        "postgresql://student_assistant:change_me_in_production@localhost:5433/student_assistant?schema=public"
    )

    # ------------------------------------------------------------------ api
    api_port: int = 5000
    api_prefix: str = "api"
    cors_origin: str | None = None
    web_port: int = 5173

    jwt_access_secret: str = "change_me_access_secret_at_least_32_chars_long"
    jwt_refresh_secret: str = "change_me_refresh_secret_at_least_32_chars_long"
    jwt_access_ttl: str = "15m"
    jwt_refresh_ttl: str = "7d"

    password_hash_memory_kib: int = 19456
    password_hash_iterations: int = 2
    password_hash_parallelism: int = 1

    max_upload_bytes: int = 26214400
    storage_root: str = "./server/storage"

    rate_limit_login_per_min: int = 5
    rate_limit_chat_per_min: int = 12
    rate_limit_default_per_min: int = 120
    rate_limit_refresh_per_min: int = 20

    # ------------------------------------------------------------- rag (legacy)
    # No longer used to reach rag-service over HTTP (the pipeline now runs
    # in-process — see app/rag_container.py). Kept only so
    # server/rag-service's own standalone process (if someone still runs it)
    # and any leftover references don't crash on a missing attribute.
    rag_service_url: str = "http://localhost:8000"
    rag_internal_token: str = "change_me_internal_token"
    rag_request_timeout_s: int = 120

    @property
    def storage_root_path(self) -> Path:
        p = Path(self.storage_root)
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p

    # ------------------------------------------------------------------ chroma
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection_prefix: str = "sa"

    # ------------------------------------------------------------ rag: models
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    preload_models: bool = False
    quantize_reranker: bool = True
    quantize_encoder: bool = True

    # ------------------------------------------------------------ rag: reader
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_s: int = 60
    gemini_max_retries: int = 2

    llm_batch_concurrency: int = 4

    # ------------------------------------------------------------ rag: chunking
    chunk_tokens: int = 400
    chunk_overlap: int = 60
    min_chunk_chars: int = 25

    # ----------------------------------------------------------- rag: retrieval
    candidates_k: int = 12
    final_k: int = 5

    max_retrieval_rounds: int = 2
    max_subqueries: int = 3

    use_llm_context: bool = True
    max_context_chunks: int = 900

    answer_threshold: float = 0.35

    @property
    def var_dir(self) -> Path:
        """Nơi lưu artefact tái tạo được: τ đã calibrate, manifest."""
        p = SERVICE_ROOT / "var"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def quantized_dir(self) -> Path:
        """Model int8 đã lượng tử hóa sẵn, dựng bởi scripts/quantize_models.py."""
        p = SERVICE_ROOT / "models_int8"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def collection(self, document_type: str) -> str:
        """Tên collection Chroma cho một loại tài liệu."""
        return f"{self.chroma_collection_prefix}_{document_type}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
