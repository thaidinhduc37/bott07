"""§5 Chunking.

Kích thước chunk là một đánh đổi bias–variance. Đoạn quá nhỏ mất ngữ cảnh cần để
diễn giải; đoạn quá lớn làm loãng embedding qua nhiều chủ đề và tiêu tốn ngân
sách chú ý của reader.

Ngân sách ở đây **đo bằng token của encoder, không phải ký tự**. Một chunk 1000
ký tự là khoảng 250 token tiếng Anh nhưng có thể vượt 500 token tiếng Việt, nên
ngân sách theo ký tự sẽ âm thầm cắt cụt một ngôn ngữ mà không cắt ngôn ngữ kia.
Với corpus quy chế và giáo trình tiếng Việt, đó không phải chi tiết nhỏ.

Việc chia là phân cấp và tôn trọng cấu trúc tài liệu: ranh giới đoạn trước, ranh
giới câu cho đoạn quá khổ, cắt cứng theo token chỉ là phương án cuối. Phần đuôi
dài `chunk_overlap` token được mang sang chunk sau để một dữ kiện nằm vắt qua
ranh giới vẫn còn nguyên trong ít nhất một chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.pipeline.ingestion import Page, articles_in_span, find_articles

# Khối bắt đầu ngay bằng tiêu đề một điều. Dùng để cắt chunk ở ranh giới điều,
# không dùng để dò danh sách điều (việc đó ở ingestion.find_articles, nơi có
# thêm bộ lọc tham chiếu chéo và ràng buộc số tăng dần).
ARTICLE_HEADING_START = re.compile(r"^[ \t]*(?:ĐIỀU|Điều|Ðiều)[ \t]+\d+[ \t]*[\.\:]")

HEADING_RE = re.compile(
    r"^\s*(?:(?:CHƯƠNG|CHUONG|PHẦN|PHAN|MỤC|MUC|CHAPTER|PART|SECTION)\b.*"
    r"|[IVXLC]+[\.\)]\s+\S.*"
    r"|\d+(?:\.\d+)*[\.\)]?\s+\S.*"
    r"|#{1,6}\s+\S.*)$",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    """Một đoạn có thể truy xuất.

    `text` là thứ reader nhìn thấy — không thêm bất kỳ nội dung tổng hợp nào.
    `prefix` và `llm_context` chỉ tham gia vào chuỗi được **nhúng**. Tách hai thứ
    này là điều làm cho trích dẫn sạch: người dùng mở nguồn ra và thấy đúng chữ
    có trong tài liệu, không thấy câu mô tả do máy viết thêm.
    """

    id: int
    text: str
    prefix: str
    source: str
    page: int
    heading: str = ""
    # Điều đầu tiên mà chunk chạm tới — chỗ người đọc nên bắt đầu tìm.
    article_number: str | None = None
    # Mọi điều chunk phủ. Nhiều hơn một phần tử nghĩa là chunk trải qua ranh giới
    # điều, và trích dẫn phải nói rõ điều đó.
    articles: list[str] = field(default_factory=list)
    llm_context: str = ""

    # Siêu dữ liệu nghiệp vụ, gắn từ phía NestJS lúc gọi /ingest.
    document_id: str = ""
    document_type: str = ""
    title: str = ""
    course_id: str | None = None

    def embed_text(self, mode: str = "structural") -> str:
        if mode == "llm" and self.llm_context:
            return f"{self.prefix} {self.llm_context}\n{self.text}"
        if mode == "raw":
            return self.text
        return f"{self.prefix}\n{self.text}"

    def payload(self) -> dict:
        """Payload lưu vào Chroma. Đây chính là nguồn của trích dẫn."""
        return {
            "chunk_id": self.id,
            "text": self.text,
            "prefix": self.prefix,
            "llm_context": self.llm_context,
            "source": self.source,
            "page": self.page,
            "heading": self.heading,
            "article_number": self.article_number,
            "articles": self.articles,
            "document_id": self.document_id,
            "document_type": self.document_type,
            "title": self.title,
            "course_id": self.course_id,
        }


class Chunker:
    def __init__(self, tokenizer, chunk_tokens: int, chunk_overlap: int, min_chunk_chars: int):
        self._tok = tokenizer
        self.chunk_tokens = chunk_tokens
        self.chunk_overlap = chunk_overlap
        self.min_chunk_chars = min_chunk_chars

    def ntokens(self, text: str) -> int:
        return len(self._tok.encode(text, add_special_tokens=False))

    # ------------------------------------------------------------------ split

    def split_blocks(self, text: str) -> list[tuple[str, int]]:
        """Đoạn văn, rồi câu, rồi cắt cứng theo token.

        Trả về `(nội_dung_khối, vị_trí_trong_text)`.

        Vị trí được mang theo chứ không tính lại về sau, vì tính lại là sai:
        chunk được ghép từ nhiều khối nối bằng `"\\n\\n"`, trong khi văn bản gốc
        có thể chỉ có một `"\\n"` ở đúng chỗ đó. Đi tìm thân chunk trong văn bản
        gốc sẽ trượt, và độ dài chunk thì dài hơn khoảng nó thực sự chiếm — cả
        hai đều làm việc gán số điều lệch về phía sau.

        Con trỏ `cursor` quét tiến, nên một câu lặp lại ở chỗ khác không kéo vị
        trí đi lung tung.
        """
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        # PDF thường chỉ có xuống dòng đơn; khi đó tách theo dòng.
        if len(paras) <= 1 and text.count("\n") > 3:
            paras = [p.strip() for p in text.split("\n") if p.strip()]

        blocks: list[tuple[str, int]] = []
        cursor = 0

        def locate(fragment: str) -> int:
            """Vị trí của `fragment` trong `text`, quét tiến từ `cursor`."""
            nonlocal cursor
            if not fragment:
                return cursor
            pos = text.find(fragment[:60], cursor)
            if pos < 0:
                pos = text.find(fragment[:30], cursor)
            if pos < 0:
                # Khối không phải chuỗi con nguyên văn (nhánh cắt cứng theo token
                # đi qua decode). Giữ nguyên con trỏ — sai vài chục ký tự ở đây
                # không đổi kết quả gán điều.
                return cursor
            cursor = pos + max(1, len(fragment) // 2)
            return pos

        for para in paras:
            para_pos = locate(para)

            if self.ntokens(para) <= self.chunk_tokens:
                blocks.append((para, para_pos))
                continue

            buf = ""
            buf_pos = para_pos
            for sentence in re.split(r"(?<=[.!?;:])\s+|\n", para):
                s = sentence.strip()
                if not s:
                    continue
                s_pos = locate(s)

                if self.ntokens(s) > self.chunk_tokens:
                    # Một "câu" dài hơn cả ngân sách: bảng, danh sách dài, hoặc
                    # văn bản thiếu dấu câu. Cắt cứng là phương án cuối.
                    if buf:
                        blocks.append((buf, buf_pos))
                        buf = ""
                    ids = self._tok.encode(s, add_special_tokens=False)
                    for i in range(0, len(ids), self.chunk_tokens):
                        piece = self._tok.decode(ids[i : i + self.chunk_tokens])
                        # Ước lượng vị trí theo tỉ lệ token đã đi qua.
                        blocks.append((piece, s_pos + int(len(s) * i / max(len(ids), 1))))
                    continue

                candidate = f"{buf} {s}".strip()
                if self.ntokens(candidate) > self.chunk_tokens:
                    blocks.append((buf, buf_pos))
                    buf, buf_pos = s, s_pos
                else:
                    if not buf:
                        buf_pos = s_pos
                    buf = candidate
            if buf:
                blocks.append((buf, buf_pos))
        return blocks

    # ------------------------------------------------------------------ chunk

    def chunk_pages(
        self,
        pages: list[Page],
        *,
        document_id: str,
        document_type: str,
        title: str,
        course_id: str | None = None,
        start_id: int = 0,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        seen: set[tuple[str, str]] = set()
        next_id = start_id
        heading_by_source: dict[str, str] = {}
        empty_pages: list[tuple[str, int]] = []

        # Điều/khoản được dò trên toàn tài liệu, không theo từng trang: một điều
        # bắt đầu ở trang 5 vẫn còn hiệu lực ở trang 6, và nếu chỉ dò trong phạm
        # vi một trang thì các trang giữa điều sẽ mất số điều.
        doc_len: dict[str, int] = {}
        doc_articles: dict[str, list[tuple[int, str]]] = {}
        page_offsets: dict[tuple[str, int], int] = {}
        for source in {p.source for p in pages}:
            group = sorted((p for p in pages if p.source == source), key=lambda p: p.page)
            buf: list[str] = []
            offset = 0
            for p in group:
                page_offsets[(source, p.page)] = offset
                buf.append(p.text)
                offset += len(p.text) + 1
            full = "\n".join(buf)
            doc_len[source] = len(full)
            doc_articles[source] = find_articles(full)

        for p in pages:
            # Tiêu đề gần nhất: quét vài dòng đầu trang, giữ lại cho các trang sau.
            for line in p.text.split("\n")[:12]:
                if HEADING_RE.match(line) and len(line.strip()) < 100:
                    heading_by_source[p.source] = line.strip()
                    break
            heading = heading_by_source.get(p.source, "")

            doc_title = title or Path(p.source).stem.replace("-", " ").replace("_", " ")
            prefix = f"[{doc_title} | trang {p.page}" + (f" | {heading}" if heading else "") + "]"

            articles = doc_articles.get(p.source, [])
            full_len = doc_len.get(p.source, 0)
            # Vị trí các khối là tương đối với trang; cộng thêm để ra vị trí
            # tuyệt đối trong tài liệu, vì `articles` được dò trên toàn tài liệu.
            page_base = page_offsets.get((p.source, p.page), 0)

            blocks = self.split_blocks(p.text)
            if not blocks:
                empty_pages.append((p.source, p.page))
                continue

            def flush(parts: list[tuple[str, int]]) -> None:
                nonlocal next_id
                body = "\n\n".join(t for t, _ in parts).strip()
                if len(body) < self.min_chunk_chars:
                    return
                key = (p.source, body)
                if key in seen:
                    return
                seen.add(key)

                # Khoảng mà chunk thực sự chiếm trong văn bản gốc: từ đầu khối
                # đầu tiên tới cuối khối cuối cùng. Không dùng len(body) vì thân
                # chunk có thêm ký tự nối giữa các khối.
                start = page_base + parts[0][1]
                last_text, last_pos = parts[-1]
                end = page_base + last_pos + len(last_text)

                covered = articles_in_span(articles, start, end, full_len)
                chunks.append(
                    Chunk(
                        id=next_id,
                        text=body,
                        prefix=prefix,
                        source=p.source,
                        page=p.page,
                        heading=heading,
                        article_number=covered[0] if covered else None,
                        articles=covered,
                        document_id=document_id,
                        document_type=document_type,
                        title=doc_title,
                        course_id=course_id,
                    )
                )
                next_id += 1

            # Vị trí tuyệt đối nơi mỗi điều bắt đầu, để nhận ra khối nào mở đầu
            # một điều mới.
            article_starts = {pos for pos, _ in articles}

            def starts_new_article(block_pos: int, block_text: str) -> bool:
                """Khối này có mở đầu một điều mới không?

                Với văn bản quy phạm, **điều** mới là đơn vị ngữ nghĩa chứ không
                phải ngân sách token. Một chunk trải từ Điều 16 sang Điều 21 vẫn
                truy xuất được, nhưng trích dẫn của nó chỉ nói được "Điều 16–21",
                và người dùng hỏi về Điều 17 nhận về một chỉ dẫn rộng gấp sáu lần
                mức cần thiết.
                """
                absolute = page_base + block_pos
                if any(absolute <= pos < absolute + max(len(block_text), 1) for pos in article_starts):
                    return True
                return bool(ARTICLE_HEADING_START.match(block_text))

            buf: list[tuple[str, int]] = []
            buf_tokens = 0

            for block in blocks:
                block_tokens = self.ntokens(block[0])

                # Cắt ở ranh giới điều kể cả khi chưa đầy ngân sách token. Đánh
                # đổi: chunk ngắn hơn, nhiều chunk hơn. Với corpus vài chục trang
                # thì chi phí đó không đáng kể so với việc trích dẫn trỏ đúng điều.
                if buf and starts_new_article(block[1], block[0]):
                    flush(buf)
                    buf, buf_tokens = [], 0

                if buf and buf_tokens + block_tokens > self.chunk_tokens:
                    flush(buf)
                    # Mang phần đuôi sang chunk sau. Bỏ phần tử đầu để chunk mới
                    # không lặp lại y hệt chunk cũ khi buf chỉ có một phần tử.
                    pending: list[tuple[str, int]] = []
                    tail_tokens = 0
                    for prev in reversed(buf[1:] if len(buf) > 1 else []):
                        t = self.ntokens(prev[0])
                        if tail_tokens + t > self.chunk_overlap:
                            break
                        pending.insert(0, prev)
                        tail_tokens += t
                    buf, buf_tokens = pending, tail_tokens
                buf.append(block)
                buf_tokens += block_tokens

            if buf:
                flush(buf)

        return chunks


@dataclass
class ChunkStats:
    count: int
    mean_tokens: float
    median_tokens: float
    min_tokens: int
    max_tokens: int
    empty_pages: list = field(default_factory=list)


def chunk_stats(chunker: Chunker, chunks: list[Chunk]) -> ChunkStats:
    import numpy as np

    if not chunks:
        return ChunkStats(0, 0.0, 0.0, 0, 0)
    lens = np.array([chunker.ntokens(c.text) for c in chunks])
    return ChunkStats(
        count=len(chunks),
        mean_tokens=float(lens.mean()),
        median_tokens=float(np.median(lens)),
        min_tokens=int(lens.min()),
        max_tokens=int(lens.max()),
    )
