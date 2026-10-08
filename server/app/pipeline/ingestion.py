"""§3 Ingestion: nguồn gốc (tên file, số trang) được gắn ngay lúc nạp, một bản ghi cho mỗi trang.

Không nối cả tài liệu rồi mới chunk: mất nguồn gốc là mất khả năng trích dẫn. Bộ nạp cũng phát hiện PDF scan ảnh (trang
gần như không ký tự) ngay tại đây thay vì sau khi đã dựng chỉ mục.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

# Dưới ngưỡng này thì gần như chắc chắn là PDF scan không có lớp văn bản.
MIN_CHARS_PER_PAGE = 100


@dataclass
class Page:
    source: str
    page: int
    text: str


class IngestionError(RuntimeError):
    pass


def load_pdf_pages(path: Path) -> list[Page]:
    doc = fitz.open(path)
    try:
        return [Page(path.name, i + 1, p.get_text("text")) for i, p in enumerate(doc)]
    finally:
        doc.close()


def load_docx(path: Path) -> list[Page]:
    """DOCX không có trang cho tới khi render nên trả một Page duy nhất (không bịa số trang). Bảng được đọc cùng đoạn
    văn vì đề cương đặt phần lớn nội dung trong bảng."""
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    parts: list[str] = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                # Khử ô bị gộp (merged cell lặp lại cùng nội dung trên nhiều cột).
                deduped: list[str] = []
                for c in cells:
                    if not deduped or deduped[-1] != c:
                        deduped.append(c)
                parts.append(" | ".join(deduped))
    return [Page(path.name, 1, "\n".join(parts))]


def load_text(path: Path) -> list[Page]:
    return [Page(path.name, 1, path.read_text(encoding="utf-8", errors="ignore"))]


def load_csv(path: Path) -> list[Page]:
    import pandas as pd

    return [Page(path.name, 1, pd.read_csv(path).to_string(index=False))]


LOADERS = {
    ".pdf": load_pdf_pages,
    ".docx": load_docx,
    ".txt": load_text,
    ".md": load_text,
    ".csv": load_csv,
}

SUPPORTED_EXTENSIONS = tuple(LOADERS)


def load_any(path: str | Path) -> list[Page]:
    p = Path(path)
    if not p.exists():
        raise IngestionError(f"Không tìm thấy tệp: {p}")
    ext = p.suffix.lower()
    loader = LOADERS.get(ext)
    if loader is None:
        # .doc (Word 97) cố tình không hỗ trợ: đọc nó cần LibreOffice hoặc
        # antiword, và im lặng trả về rác nhị phân thì tệ hơn là báo lỗi rõ.
        raise IngestionError(
            f"Định dạng {ext} chưa được hỗ trợ. Định dạng nhận được: "
            f"{', '.join(SUPPORTED_EXTENSIONS)}. "
            "Với tệp .doc cũ, hãy lưu lại thành .docx trước khi nạp."
        )
    return loader(p)


@dataclass
class IngestionReport:
    source: str
    pages: int
    chars: int
    chars_per_page: int
    likely_scanned: bool
    warning: str | None = None


def load_and_report(path: str | Path) -> tuple[list[Page], IngestionReport]:
    pages = load_any(path)
    chars = sum(len(p.text) for p in pages)
    per_page = round(chars / max(len(pages), 1))
    scanned = per_page < MIN_CHARS_PER_PAGE

    if not pages or chars == 0:
        raise IngestionError(
            f"{Path(path).name}: trích xuất được 0 ký tự. "
            "Nhiều khả năng đây là bản scan ảnh và cần OCR trước khi nạp."
        )

    warning = None
    if scanned:
        warning = (
            f"{Path(path).name} chỉ cho {per_page} ký tự mỗi trang. "
            "Nhiều khả năng đây là PDF scan không có lớp văn bản; kết quả truy "
            "xuất sẽ rất kém."
        )

    return pages, IngestionReport(
        source=Path(path).name,
        pages=len(pages),
        chars=chars,
        chars_per_page=per_page,
        likely_scanned=scanned,
        warning=warning,
    )


# ---------------------------------------------------------------------------
#  Nhận diện điều/khoản — cần cho trích dẫn quy chế
# ---------------------------------------------------------------------------

# Tiêu đề điều: "Điều 12." hoặc "Điều 12:" kèm tên điều. `(?=[^\n]{3,})` bắt buộc để không khớp tham chiếu chéo bị PDF
# ngắt xuống đầu dòng ("...theo điểm e Khoản 2,\nĐiều 2 của Quy chế này."): nhận nhầm sẽ làm hỏng nhãn mọi chunk sau.
ARTICLE_RE = re.compile(
    # Cho phép tiền tố tiêu đề Markdown ("## Điều 27.") và chữ đậm ("**Điều 27.**"):
    # tài liệu nạp dạng .md viết tiêu đề điều như vậy; trước đây chúng không bao
    # giờ khớp và cả văn bản mất nhãn điều.
    r"^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*|__)?[ \t]*(?:ĐIỀU|Điều|Ðiều)[ \t]+(\d+)[ \t]*[\.\:][ \t]*(?=[^\n]{3,})",
    re.MULTILINE,
)

# Dòng mục lục: "Điều 27. Chuyển chương trình, ngành đào tạo … 22" — kết thúc bằng
# số trang và không phải tiêu đề Markdown.
TOC_LINE_END = re.compile(r"[ \t\.…]+\d{1,4}[ \t]*$")

# Cụm mở đầu một tham chiếu chéo. "Điều 12 của Quy chế này", "Điều 2 nêu trên".
CROSS_REFERENCE_TAIL = re.compile(r"^\s*(?:của|nêu|này|trên|tại|và|,)", re.IGNORECASE)


def find_articles(text: str) -> list[tuple[int, str]]:
    """[(vị_trí_ký_tự, "Điều 12"), ...] các chỗ bắt đầu một điều (quy chế được viện dẫn theo điều, không theo trang).

    Ba bộ lọc: bỏ chỗ ngay sau số điều là "của", "này", "nêu trên" (đó là tham chiếu); số điều phải tăng dần ("Điều 2" sau
    "Điều 16" là tham chiếu chéo); bỏ dòng mục lục (kết thúc bằng số trang) khi cùng số điều còn xuất hiện lại phía sau, để
    "Điều 5. Thang điểm 10" không bị bỏ nhầm.
    """
    candidates: list[tuple[int, int, bool]] = []
    for m in ARTICLE_RE.finditer(text):
        tail = text[m.end() : m.end() + 12]
        if CROSS_REFERENCE_TAIL.match(tail):
            continue
        line_end = text.find("\n", m.start())
        line = text[m.start() : line_end if line_end != -1 else len(text)]
        looks_toc = not line.lstrip().startswith("#") and bool(TOC_LINE_END.search(line))
        candidates.append((m.start(), int(m.group(1)), looks_toc))

    raw: list[tuple[int, int]] = []
    for i, (pos, number, looks_toc) in enumerate(candidates):
        if looks_toc and any(n == number for _, n, _ in candidates[i + 1 :]):
            continue
        raw.append((pos, number))

    articles: list[tuple[int, str]] = []
    highest = 0
    for pos, number in raw:
        if number <= highest:
            continue  # số lùi lại → tham chiếu chéo, không phải tiêu đề
        highest = number
        articles.append((pos, f"Điều {number}"))
    return articles


def article_at(articles: list[tuple[int, str]], offset: int) -> str | None:
    """Điều đang có hiệu lực tại vị trí `offset` (điều gần nhất bắt đầu trước đó)."""
    found = None
    for pos, label in articles:
        if pos <= offset:
            found = label
        else:
            break
    return found


def articles_in_span(
    articles: list[tuple[int, str]],
    start: int,
    end: int,
    text_length: int,
) -> list[str]:
    """Mọi điều mà khoảng [start, end) chạm tới, theo thứ tự văn bản.

    Một chunk có thể phủ nhiều điều; ép về một nhãn là mất thông tin. Bên gọi lấy phần tử đầu làm nhãn hiển thị và giữ phần
    còn lại để nói chunk trải tới đâu.
    """
    if not articles or end <= start:
        found = article_at(articles, start)
        return [found] if found else []

    spans: list[tuple[int, int, str]] = []
    for i, (pos, label) in enumerate(articles):
        next_pos = articles[i + 1][0] if i + 1 < len(articles) else text_length
        spans.append((pos, next_pos, label))

    covered = [
        label
        for span_start, span_end, label in spans
        if min(end, span_end) > max(start, span_start)
    ]
    if covered:
        return covered
    found = article_at(articles, start)
    return [found] if found else []
