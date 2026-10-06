"""In-process RAG pipeline container.

Port of `server/rag-service/app/deps.py`'s `Container`/`build_reader`. The
pipeline used to run as its own FastAPI process (`rag-service`), reached over
HTTP by `api-py`/`rag_client.py`. Now everything is one process: this module
builds the same objects (model registry, Chroma store, LLM reader chain,
retriever, orchestrator, indexing service) once at startup, and
`app/services/rag_client.py` calls them directly in Python — no HTTP, no
`X-Internal-Token`, no second process.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings, get_settings
from app.pipeline.indexing import IndexingService
from app.pipeline.llm import BaseReader, GeminiReader
from app.pipeline.models import ModelRegistry
from app.pipeline.orchestrator import Orchestrator
from app.pipeline.retrieval import Retriever
from app.store.chroma_store import ChromaStore

log = logging.getLogger("rag.container")


def build_reader(settings: Settings) -> BaseReader:
    """Dựng reader Gemini — nhà cung cấp mô hình ngôn ngữ duy nhất."""
    reader = GeminiReader(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_s=settings.gemini_timeout_s,
        max_retries=settings.gemini_max_retries,
        concurrency=settings.llm_batch_concurrency,
    )
    if not reader.available:
        log.warning(
            "Chưa cấu hình GEMINI_API_KEY. "
            "Truy xuất và cổng từ chối vẫn chạy; phần sinh câu trả lời sẽ báo lỗi."
        )
    return reader


class RagContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.models = ModelRegistry(
            settings.embedding_model,
            settings.reranker_model,
            quantize_reranker=settings.quantize_reranker,
            quantize_encoder=settings.quantize_encoder,
            quantized_dir=settings.quantized_dir,
        )
        self.store = ChromaStore(settings.chroma_host, settings.chroma_port, settings.embedding_dim)
        self.reader = build_reader(settings)
        self.retriever = Retriever(self.models, self.store, settings)
        self.orchestrator = Orchestrator(self.retriever, self.reader, settings)
        self.indexing = IndexingService(self.models, self.store, self.reader, settings)

    # ------------------------------------------------------------------ startup

    def corpus_topics(self, document_type: str) -> str:
        """Tên các tài liệu trong một collection, dùng cho lời từ chối."""
        collection = self.settings.collection(document_type)
        payloads = self.store.scroll_all(collection)
        titles = {
            p.get("title") or Path(p.get("source", "")).stem
            for p in payloads
        }
        return ", ".join(sorted(t for t in titles if t))


_container: RagContainer | None = None


def get_rag_container() -> RagContainer:
    global _container
    if _container is None:
        _container = RagContainer(get_settings())
    return _container


# --------------------------------------------------------------- file paths

def repo_root() -> Path:
    from app.config import REPO_ROOT

    return REPO_ROOT


def resolve_under_repo(relative: str) -> Path:
    """Giải một đường dẫn tương đối, buộc nó nằm trong server/storage/ hoặc
    server/data/. Port của `rag-service/app/deps.py:resolve_under_repo` — vẫn
    cần dù giờ chạy trong cùng process, vì `file_path` vẫn tới từ dữ liệu
    người dùng (tên tệp đã lưu qua `StorageService`), không phải mã nguồn tin
    cậy."""
    root = repo_root().resolve()
    allowed_roots = [(root / "server" / "storage").resolve(), (root / "server" / "data").resolve()]
    candidate = (root / relative).resolve()
    if not any(candidate.is_relative_to(allowed) for allowed in allowed_roots):
        raise ValueError(f"Đường dẫn nằm ngoài phạm vi cho phép: {relative}")
    if not candidate.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp: {relative}")
    return candidate
