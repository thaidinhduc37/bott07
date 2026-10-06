"""§7 Chỉ mục dense — ChromaDB.

Notebook giữ embedding trong một ma trận numpy và tìm kiếm tích vô hướng chính
xác trên toàn bộ ma trận. Ở quy mô của notebook đó là lựa chọn đúng: chỉ mục xấp
xỉ (HNSW, IVF) đánh đổi recall lấy tốc độ mà không có lợi ích độ trễ nào đáng kể.

Ở đây phải đổi sang một kho vector chạy như dịch vụ vì một lý do khác hẳn: **chỉ
mục phải sống sót qua lần khởi động lại**. Notebook dựng lại chỉ mục mỗi lần
chạy; một dịch vụ thì không thể bắt cán bộ nạp lại toàn bộ giáo trình mỗi lần
container restart.

Trước đây dùng Qdrant; nay đổi sang ChromaDB (nhẹ hơn, đủ dùng cho quy mô dev
của dự án này) chạy như container Docker ở chế độ server, dịch vụ RAG (chạy
native trên host) nối vào qua `HttpClient`. Cùng dùng HNSW nên đánh đổi recall
tương tự Qdrant.

Chroma chỉ chấp nhận `str | int | float | bool` làm giá trị metadata — không
`None`, không `list`. `_encode_metadata`/`_decode_metadata` làm việc chuyển đổi
hai chiều giữa payload nội bộ (giữ nguyên hình dạng cũ, tương thích với phần còn
lại của pipeline) và metadata Chroma chấp nhận được.
"""

from __future__ import annotations

import json
import logging
import uuid

import chromadb

from app.pipeline.chunking import Chunk

log = logging.getLogger("rag.chroma")

# Trường có thể là None ở payload gốc; Chroma không nhận None nên mã hóa thành
# chuỗi rỗng và giải mã ngược lại None khi đọc ra.
_NULLABLE_STR_FIELDS = ("article_number", "course_id")


def _encode_metadata(payload: dict) -> dict:
    meta = dict(payload)
    meta["articles"] = json.dumps(meta.get("articles") or [], ensure_ascii=False)
    for field in _NULLABLE_STR_FIELDS:
        if meta.get(field) is None:
            meta[field] = ""
    # Chroma từ chối bất kỳ giá trị None nào trong metadata; dọn nốt trường lạ.
    return {k: v for k, v in meta.items() if v is not None}


def _decode_metadata(meta: dict) -> dict:
    payload = dict(meta)
    raw_articles = payload.get("articles")
    try:
        payload["articles"] = json.loads(raw_articles) if raw_articles else []
    except (TypeError, ValueError):
        payload["articles"] = []
    for field in _NULLABLE_STR_FIELDS:
        if payload.get(field) == "":
            payload[field] = None
    return payload


class ChromaStore:
    def __init__(self, host: str, port: int, dim: int):
        self.client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        self.dim = dim
        self._titles_cache: dict[str, tuple[int, dict[str, str]]] = {}

    # -------------------------------------------------------------- collection

    def _exists(self, name: str) -> bool:
        return any(c.name == name for c in self.client.list_collections())

    def ensure_collection(self, name: str):
        # `embedding_function=None`: mọi vector đều do dịch vụ RAG tính sẵn
        # (BGE-M3) và truyền thẳng vào; không cần Chroma tự nhúng (điều đó sẽ
        # kéo về một model mặc định khác, và không khớp không gian embedding).
        return self.client.get_or_create_collection(
            name=name,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )

    def collection_info(self, name: str) -> dict | None:
        if not self._exists(name):
            return None
        col = self.client.get_collection(name=name, embedding_function=None)
        return {"points": col.count(), "status": "green"}

    # ------------------------------------------------------------------ upsert

    def upsert_chunks(self, collection: str, chunks: list[Chunk], vectors) -> int:
        col = self.ensure_collection(collection)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{c.document_id}/{c.id}")) for c in chunks]
        metadatas = [_encode_metadata(c.payload()) for c in chunks]
        embeddings = [vectors[i].tolist() for i in range(len(chunks))]
        documents = [c.text for c in chunks]

        # Chia lô như bên Qdrant: một lần upsert vài nghìn vector 1024 chiều là
        # payload HTTP hàng chục MB.
        BATCH = 128
        for i in range(0, len(ids), BATCH):
            j = i + BATCH
            col.upsert(
                ids=ids[i:j],
                embeddings=embeddings[i:j],
                metadatas=metadatas[i:j],
                documents=documents[i:j],
            )
        return len(ids)

    # ------------------------------------------------------------------ search

    def document_titles(self, collection: str) -> dict[str, str]:
        """{document_id: title} của mọi tài liệu trong collection.

        Dùng để nhận ra tài liệu mà câu hỏi nhắc tên. Đọc metadata của cả
        collection nên được nhớ lại theo số điểm hiện có: nạp thêm hay xóa tài
        liệu đổi số điểm thì lần gọi sau tự đọc lại.
        """
        if not self._exists(collection):
            return {}
        col = self.client.get_collection(name=collection, embedding_function=None)
        count = col.count()
        cached = self._titles_cache.get(collection)
        if cached and cached[0] == count:
            return cached[1]
        got = col.get(include=["metadatas"], limit=max(count, 1))
        titles: dict[str, str] = {}
        for meta in got.get("metadatas") or []:
            doc_id, title = meta.get("document_id"), meta.get("title")
            if doc_id and title:
                titles[doc_id] = title
        self._titles_cache[collection] = (count, titles)
        return titles

    def search(
        self,
        collection: str,
        vector,
        limit: int,
        course_id: str | None = None,
        document_ids: list[str] | None = None,
    ) -> list[tuple[dict, float]]:
        if not self._exists(collection):
            return []
        col = self.client.get_collection(name=collection, embedding_function=None)

        clauses = []
        if course_id:
            clauses.append({"course_id": course_id})
        if document_ids:
            clauses.append({"document_id": {"$in": list(document_ids)}})
        where = None if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}
        res = col.query(
            query_embeddings=[vector.tolist()],
            n_results=limit,
            where=where,
            include=["metadatas", "distances"],
        )
        metadatas = res.get("metadatas") or [[]]
        distances = res.get("distances") or [[]]
        out: list[tuple[dict, float]] = []
        for meta, dist in zip(metadatas[0], distances[0]):
            # Chroma trả cosine *distance*; Qdrant trả cosine *similarity*. Đổi
            # lại về similarity (1 - distance) để phần còn lại của pipeline
            # (RRF, log, hiển thị) không phải biết kho vector nào đang chạy phía
            # sau.
            out.append((_decode_metadata(meta), 1.0 - float(dist)))
        return out

    def scroll_all(self, collection: str, document_id: str | None = None) -> list[dict]:
        """Lấy toàn bộ payload của một collection (vd. dùng cho `corpus_topics`)."""
        if not self._exists(collection):
            return []
        col = self.client.get_collection(name=collection, embedding_function=None)

        where = {"document_id": document_id} if document_id else None
        out: list[dict] = []
        BATCH = 256
        offset = 0
        while True:
            res = col.get(where=where, limit=BATCH, offset=offset, include=["metadatas"])
            metadatas = res.get("metadatas") or []
            if not metadatas:
                break
            out.extend(_decode_metadata(m) for m in metadatas)
            if len(metadatas) < BATCH:
                break
            offset += BATCH
        return out

    # ------------------------------------------------------------------ delete

    def delete_document(self, collection: str, document_id: str) -> int:
        """Xóa mọi điểm thuộc một tài liệu.

        Trả về số điểm đã xóa để phía api-py đối chiếu: nếu PostgreSQL nói tài
        liệu có 240 chunk mà ở đây xóa được 0, thì hai bên đã lệch nhau và phải
        báo chứ không được im lặng coi như thành công.
        """
        if not self._exists(collection):
            return 0
        before = len(self.scroll_all(collection, document_id))
        if before == 0:
            return 0
        col = self.client.get_collection(name=collection, embedding_function=None)
        col.delete(where={"document_id": document_id})
        return before

    def health(self) -> tuple[bool, str]:
        try:
            self.client.heartbeat()
            n = len(self.client.list_collections())
            return True, f"{n} collection"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
