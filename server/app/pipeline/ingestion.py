"""§3 Ingestion — nguồn gốc được thiết lập ở đây hoặc không bao giờ.

Một đoạn văn được truy xuất chỉ có ích nếu hệ thống nói được nó đến từ đâu.
Nguồn gốc không thể tái tạo về sau, nên nó được gắn ngay lúc nạp: **một bản ghi
cho mỗi trang**, mang theo tên file và số trang; mọi cấu trúc phía sau kế thừa
các trường đó.

Nối cả tài liệu thành một chuỗi rồi mới chunk — lối tắt phổ biến nhất trong các
hướng dẫn RAG — phá hủy điều này không thể đảo ngược, và cùng với nó là mọi khả
năng trích dẫn thật.

Bộ nạp cũng kiểm tra xem việc trích xuất có thực sự cho ra chữ hay không. PDF
scan ảnh trả về các trang gần như không ký tự; phát hiện ở đây thay vì sau khi
đã dựng xong chỉ mục tiết kiệm rất nhiều nhầm lẫn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
    """DOCX không có khái niệm trang cho tới khi được render.

    Trả về một Page duy nhất là trung thực: bịa ra số trang bằng cách đếm ký tự
    sẽ tạo ra trích dẫn trỏ tới trang không tồn tại — tệ hơn là không có số trang.
    Bảng được đọc cùng với đoạn văn vì đề cương học phần đặt phần lớn nội dung
    trong bảng.
    """
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

# Tiêu đề điều: "Điều 12." hoặc "Điều 12:" theo sau là tên điều.
#
# Phần `(?=[^\n]{3,})` là bắt buộc. Không có nó, mẫu này khớp cả tham chiếu chéo
# — và PDF ngắt dòng thường xuyên đẩy chúng xuống đầu dòng:
#
#     ...theo quy định tại điểm e Khoản 2,
#     Điều 2 của Quy chế này.
#
# Ở đây "Điều 2" nằm đầu dòng nhưng là một tham chiếu, không phải chỗ bắt đầu
# Điều 2. Nhận nhầm nó làm hỏng nhãn của mọi chunk phía sau.
ARTICLE_RE = re.compile(
    r"^[ \t]*(?:ĐIỀU|Điều|Ðiều)[ \t]+(\d+)[ \t]*[\.\:][ \t]*(?=[^\n]{3,})",
    re.MULTILINE,
)

# Cụm mở đầu một tham chiếu chéo. "Điều 12 của Quy chế này", "Điều 2 nêu trên".
CROSS_REFERENCE_TAIL = re.compile(r"^\s*(?:của|nêu|này|trên|tại|và|,)", re.IGNORECASE)


def find_articles(text: str) -> list[tuple[int, str]]:
    """Trả về [(vị_trí_ký_tự, "Điều 12"), ...] các chỗ **bắt đầu** một điều.

    Quy chế được viện dẫn theo điều chứ không theo trang: "Điều 12 khoản 3" là
    thứ người đọc tra lại được, còn "trang 7" thì phụ thuộc bản in. Cả hai đều
    được lưu, nhưng số điều là cái phải đúng.

    Hai bộ lọc, vì một mình biểu thức chính quy không đủ:

    1. **Đuôi tham chiếu.** Bỏ những chỗ mà ngay sau số điều là "của", "này",
       "nêu trên" — đó là cách người ta viện dẫn, không phải cách người ta mở đầu
       một điều.

    2. **Số điều phải tăng dần.** Văn bản quy phạm đánh số điều tuần tự. "Điều 2"
       xuất hiện sau "Điều 16" chắc chắn là tham chiếu chéo. Ràng buộc này bắt
       được cả những trường hợp mà bộ lọc đuôi bỏ lọt.
    """
    raw: list[tuple[int, int]] = []
    for m in ARTICLE_RE.finditer(text):
        tail = text[m.end() : m.end() + 12]
        if CROSS_REFERENCE_TAIL.match(tail):
            continue
        raw.append((m.start(), int(m.group(1))))

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

    Một chunk 400 token thường phủ nhiều hơn một điều — ở cuối quy chế, nơi các
    điều chỉ dài vài dòng, một chunk có thể phủ trọn bốn điều. Ép về một nhãn
    duy nhất là làm mất thông tin dù chọn quy tắc nào:

    * Lấy điều ở vị trí bắt đầu → bỏ qua ba điều còn lại.
    * Lấy điều chiếm nhiều ký tự nhất → một chunk mở đầu bằng "Điều 17." bị gán
      "Điều 20" chỉ vì Điều 20 dài hơn, và người bấm vào trích dẫn tới nhầm chỗ.

    Nên trả về cả danh sách. Bên gọi lấy phần tử đầu làm nhãn hiển thị — đó là
    chỗ người đọc nên bắt đầu tìm — và giữ phần còn lại để nói rõ chunk trải dài
    tới đâu.
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
