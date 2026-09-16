"""§6 Contextualisation và luồng ingest đầy đủ.

**Vì sao cần contextualise.** Một chunk tách khỏi tài liệu của nó thường không tự
diễn giải được. "Quy định này chỉ áp dụng cho trường hợp thứ hai" hay một dòng
bảng trần mang gần như không tín hiệu truy xuất nào, dù nó có thể chứa đúng câu
trả lời. Cách chữa là **nhúng một dạng đã được đặt vào ngữ cảnh** của chunk trong
khi vẫn cho reader xem văn bản gốc, để trích dẫn giữ được sự sạch sẽ.

Hai biến thể, đúng như notebook:

*Cấu trúc (tất định, miễn phí).* Ghép tiêu đề tài liệu, số trang và đề mục gần
nhất vào trước. Không tốn gì và luôn áp dụng được.

*LLM viết.* Reader được xem chunk cùng một cửa sổ văn bản xung quanh và được yêu
cầu viết một câu định vị. Đây là *contextual retrieval*; nó thường cho mức tăng
recall lớn nhất so với chi phí, nhưng đòi hỏi một lời gọi sinh cho mỗi chunk lúc
lập chỉ mục. Vì mỗi lời gọi bây giờ là tiền và quota thật, nó bị chặn bởi
`MAX_CONTEXT_CHUNKS` và tự tắt khi vượt ngưỡng.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.pipeline import blocking, prompts
from app.pipeline.chunking import Chunk, Chunker
from app.pipeline.ingestion import Page, load_and_report
from app.pipeline.llm import BaseReader
from app.pipeline.normalisation import strip_boilerplate

log = logging.getLogger("rag.indexing")

CONTEXT_WINDOW_CHARS = 2500


@dataclass
class IngestReport:
    document_id: str
    source: str
    pages: int
    chars: int
    chars_per_page: int
    likely_scanned: bool
    chunks: int
    contextualised: int
    points_upserted: int
    collection: str
    seconds: float
    warnings: list[str] = field(default_factory=list)
    normalisation: dict = field(default_factory=dict)
    chunk_tokens: dict = field(default_factory=dict)


async def contextualise(
    chunks: list[Chunk],
    pages: list[Page],
    reader: BaseReader,
    max_chunks: int,
) -> tuple[int, list[str]]:
    """Cho LLM viết một câu định vị cho mỗi chunk. Trả (số thành công, cảnh báo)."""
    warnings: list[str] = []

    if not reader.available:
        warnings.append(
            "Chưa có GEMINI_API_KEY nên bỏ qua bước LLM viết ngữ cảnh; "
            "chỉ dùng tiền tố cấu trúc. Recall sẽ thấp hơn."
        )
        return 0, warnings

    if len(chunks) > max_chunks:
        warnings.append(
            f"{len(chunks)} chunk vượt ngưỡng MAX_CONTEXT_CHUNKS={max_chunks}; "
            "bỏ qua bước LLM viết ngữ cảnh để chặn thời gian và chi phí lập chỉ mục."
        )
        return 0, warnings

    doc_text: dict[str, str] = defaultdict(str)
    for p in pages:
        doc_text[p.source] += p.text + "\n"

    prompt_list: list[str] = []
    for c in chunks:
        doc = doc_text[c.source]
        centre = doc.find(c.text[:80])
        lo = max(0, (centre if centre >= 0 else 0) - CONTEXT_WINDOW_CHARS // 2)
        prompt_list.append(
            prompts.CONTEXT_PROMPT.format(
                doc=doc[lo : lo + CONTEXT_WINDOW_CHARS], chunk=c.text[:1500]
            )
        )

    t0 = time.time()
    results = await reader.batch(prompt_list, max_output_tokens=64, tag="contextualise")
    ok = 0
    for c, out in zip(chunks, results):
        if out:
            c.llm_context = out.split("\n")[0].strip().strip('"')[:250]
            ok += 1

    log.info("Đã viết ngữ cảnh cho %d/%d chunk trong %.1fs", ok, len(chunks), time.time() - t0)
    if ok < len(chunks):
        warnings.append(
            f"{len(chunks) - ok} chunk không viết được ngữ cảnh (LLM lỗi hoặc timeout); "
            "các chunk đó chỉ dùng tiền tố cấu trúc."
        )
    return ok, warnings


class IndexingService:
    def __init__(self, models, store, reader, settings):
        self.models = models
        self.store = store
        self.reader = reader
        self.settings = settings

    def _chunker(self) -> Chunker:
        return Chunker(
            tokenizer=self.models.tokenizer,
            chunk_tokens=self.settings.chunk_tokens,
            chunk_overlap=self.settings.chunk_overlap,
            min_chunk_chars=self.settings.min_chunk_chars,
        )

    async def ingest(
        self,
        *,
        file_path: str,
        document_id: str,
        document_type: str,
        title: str,
        course_id: str | None = None,
    ) -> IngestReport:
        t0 = time.time()
        collection = self.settings.collection(document_type)
        warnings: list[str] = []

        # --- §3 nạp, giữ nguồn gốc ---------------------------------------
        pages, ing = load_and_report(file_path)
        if ing.warning:
            warnings.append(ing.warning)

        # --- §4 chuẩn hóa -------------------------------------------------
        pages, norm = strip_boilerplate(pages)
        if norm.rejected:
            warnings.append(
                "Bước lọc tiêu đề/chân trang bị hủy vì nó xóa quá nửa văn bản; "
                "giữ nguyên trang gốc."
            )

        # --- §5 chunk theo token của encoder -------------------------------
        chunker = self._chunker()
        chunks = chunker.chunk_pages(
            pages,
            document_id=document_id,
            document_type=document_type,
            title=title,
            course_id=course_id,
        )
        if not chunks:
            raise RuntimeError(
                f"Không tạo được chunk nào từ {ing.pages} trang. "
                "Kiểm tra xem tệp có thực sự chứa văn bản không."
            )

        from app.pipeline.chunking import chunk_stats

        stats = chunk_stats(chunker, chunks)

        # --- §6 contextualise ---------------------------------------------
        contextualised = 0
        if self.settings.use_llm_context:
            contextualised, ctx_warnings = await contextualise(
                chunks, pages, self.reader, self.settings.max_context_chunks
            )
            warnings.extend(ctx_warnings)

        # --- §7 nhúng và lập chỉ mục ---------------------------------------
        mode = "llm" if contextualised > 0 else "structural"
        # Nhúng cả tài liệu là việc dài nhất trong dịch vụ — đo được 615 giây cho
        # một giáo trình PDF 1 MB. Chạy nó trên event loop làm treo toàn bộ dịch
        # vụ, kể cả /health, cho tới khi xong.
        #
        # Cắt thành lô thay vì gọi encode một lần: luồng worker chỉ có một, nên
        # một lời gọi mười phút sẽ bắt mọi truy vấn của học viên xếp hàng sau nó
        # và NestJS sẽ hết giờ ở giây 120. Chia lô thì truy vấn đến giữa chừng
        # chỉ phải chờ hết một lô. Việc nạp không chậm đi — vẫn từng ấy chunk,
        # chỉ khác chỗ nhả quyền điều khiển.
        # Lô 8 để khớp `batch_size` nội bộ của encoder: nhỏ hơn thì phí một lượt
        # gọi cho mỗi lô, lớn hơn thì giữ luồng worker lâu hơn mà không nhúng
        # nhanh thêm — encoder vẫn cắt thành lô 8 ở bên trong.
        texts = [c.embed_text(mode) for c in chunks]
        EMBED_BATCH = 8
        parts = [
            await blocking.run(self.models.encode, texts[i : i + EMBED_BATCH])
            for i in range(0, len(texts), EMBED_BATCH)
        ]
        vectors = parts[0] if len(parts) == 1 else np.vstack(parts)
        points = self.store.upsert_chunks(collection, chunks, vectors)

        return IngestReport(
            document_id=document_id,
            source=Path(file_path).name,
            pages=ing.pages,
            chars=ing.chars,
            chars_per_page=ing.chars_per_page,
            likely_scanned=ing.likely_scanned,
            chunks=len(chunks),
            contextualised=contextualised,
            points_upserted=points,
            collection=collection,
            seconds=round(time.time() - t0, 2),
            warnings=warnings,
            normalisation=norm.as_dict(),
            chunk_tokens={
                "mean": round(stats.mean_tokens, 1),
                "median": round(stats.median_tokens, 1),
                "min": stats.min_tokens,
                "max": stats.max_tokens,
            },
        )

    # ------------------------------------------------------------------ delete

    def delete_document(self, document_id: str, document_type: str | None = None) -> dict:
        """Xóa một tài liệu khỏi chỉ mục dense.

        Không biết loại tài liệu thì quét cả hai collection: thà làm thừa một
        truy vấn còn hơn để lại vector mồ côi mà về sau vẫn được trích dẫn cho
        một tài liệu PostgreSQL đã coi là đã xóa.
        """
        types = [document_type] if document_type else ["quyche", "giaotrinh"]
        removed: dict[str, int] = {}
        for t in types:
            collection = self.settings.collection(t)
            count = self.store.delete_document(collection, document_id)
            removed[collection] = count
        return {"document_id": document_id, "removed": removed, "total": sum(removed.values())}
