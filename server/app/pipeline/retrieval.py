"""§10–§11 Xếp lại hạng, và giao diện truy xuất.

Truy xuất chỉ còn một tầng dense (Chroma). Hợp nhất RRF với BM25 đã bị bỏ —
xem lịch sử git nếu cần lại retrieval thưa.

**Rerank (§10).** Truy xuất tầng một so vector truy vấn với vector đoạn văn được
tính độc lập với nó. Cross-encoder thì đọc cặp đã nối và cho ra một điểm liên
quan duy nhất, nên xử lý được phủ định, mệnh đề giới hạn và sai lệch thực thể mà
độ tương tự vector không làm được. Chạy nó trên toàn corpus thì quá đắt, nhưng
trên vài chục ứng viên thì hoàn toàn chấp nhận được.

Hai hệ quả quan trọng. Thứ nhất, mức tăng độ chính xác thường lớn nhất trong các
thành phần. Thứ hai — và ít được khai thác hơn — điểm số của nó **đủ được
calibrate để đặt ngưỡng**, và đó là thứ làm cho cơ chế abstention ở §14 khả thi.
Điểm tương tự của tầng một không dùng được cho việc này: giá trị tuyệt đối của
chúng mang tính tương đối theo corpus, và một truy vấn vô nghĩa vẫn trả về láng
giềng gần nhất với cosine trông rất khả quan.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("rag.retrieval")


def _fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt, mọi ký tự không phải chữ/số thành một dấu cách."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


_TITLE_NOISE_PREFIX = re.compile(r"^(?:(?:\d+|k\d+)\s+)+")


def _title_key(title: str) -> str:
    """Khóa so khớp của một tiêu đề tài liệu: bỏ phần trong ngoặc, bỏ dấu, bỏ số thứ
    tự và nhãn khóa ở đầu ("33 Co So Du Lieu" -> "co so du lieu")."""
    return _TITLE_NOISE_PREFIX.sub("", _fold(re.sub(r"\(.*?\)", " ", title)))


@dataclass
class Hit:
    payload: dict
    score: float
    rank: int

    @property
    def text(self) -> str:
        return self.payload.get("text", "")

    def citation(self, marker: int) -> dict:
        """Trích dẫn hiển thị cho người dùng.

        Trả cả `page` lẫn `article_number`: quy chế được viện dẫn theo điều
        ("Điều 12"), giáo trình được viện dẫn theo trang. Trường nào không có thì
        để trống chứ không bịa.

        Khi một đoạn trải qua nhiều điều, `article_range` nói rõ ("Điều 17–20").
        Ghi một số điều duy nhất cho một đoạn phủ bốn điều là một trích dẫn sai
        theo cách khó phát hiện: nó trỏ tới một chỗ có thật, chỉ là không phải
        chỗ chứa câu trả lời.
        """
        articles = self.payload.get("articles") or []
        article_range = None
        if len(articles) > 1:
            first = articles[0].replace("Điều ", "")
            last = articles[-1].replace("Điều ", "")
            article_range = f"Điều {first}–{last}"

        # Tệp markdown/văn bản thuần không có trang thật (trình nạp gán mọi đoạn
        # vào "trang 1"). Trả số đó cho người dùng là một chỉ dẫn sai; để trống
        # để giao diện chỉ hiện số điều và tên tài liệu.
        source = str(self.payload.get("source", "")).lower()
        page = None if source.endswith((".md", ".txt")) else self.payload.get("page")

        return {
            "marker": marker,
            "document_id": self.payload.get("document_id"),
            "document_title": self.payload.get("title") or self.payload.get("source", ""),
            "source_file": self.payload.get("source", ""),
            "page": page,
            "article_number": self.payload.get("article_number"),
            "article_range": article_range,
            "rerank_score": round(self.score, 4),
            "snippet": self.text[:300],
        }


class Retriever:
    """Truy xuất dense (Chroma), rồi xếp lại hạng."""

    def __init__(self, models, store, settings):
        self.models = models
        self.store = store
        self.settings = settings

    def scope_documents(self, query: str, collection: str) -> list[str] | None:
        """Các tài liệu mà câu hỏi nhắc tên, hoặc None nếu không nhắc tài liệu nào.

        Phần đầu của các đề cương học phần có văn phong gần như giống hệt nhau, nên
        câu như "học phần tiên quyết của Cơ sở dữ liệu" bị hàng chục đề cương khác
        chen vào top ứng viên và đoạn của đúng môn tụt xuống hạng 20-50. Khi câu
        hỏi nêu nguyên văn tên một tài liệu (không phân biệt dấu, hoa thường) thì
        thu hẹp việc tìm vào đúng tài liệu đó.

        Chỉ giữ lần xuất hiện dài nhất: "Hệ quản trị cơ sở dữ liệu" chứa "cơ sở dữ
        liệu", nhưng nhắc tên môn dài thì không có nghĩa là hỏi cả môn ngắn. Nếu
        tên ngắn còn xuất hiện ở chỗ khác trong câu thì vẫn được tính.
        """
        titles = self.store.document_titles(collection)
        if not titles:
            return None
        folded = _fold(query)
        ids_by_key: dict[str, list[str]] = {}
        for doc_id, title in titles.items():
            key = _title_key(title)
            if len(key) >= 6 and " " in key:
                ids_by_key.setdefault(key, []).append(doc_id)

        spans: list[tuple[int, int, str]] = []
        for key in ids_by_key:
            for m in re.finditer(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", folded):
                spans.append((m.start(), m.end(), key))
        kept = {
            key
            for start, end, key in spans
            if not any(s <= start and end <= e and (e - s) > (end - start) for s, e, _ in spans)
        }
        if not kept:
            return None
        log.info("Phạm vi tài liệu theo tên trong câu hỏi: %s", sorted(kept))
        return [doc_id for key in sorted(kept) for doc_id in ids_by_key[key]]

    def candidates(
        self,
        query: str,
        collection: str,
        n: int,
        course_id: str | None = None,
    ) -> list[dict]:
        vector = self.models.encode([query])[0]
        scope = None if course_id else self.scope_documents(query, collection)
        if scope:
            scoped = self.store.search(collection, vector, n, document_ids=scope)
            # Tài liệu được nhắc tên mà gần như không có đoạn nào: coi như nhận
            # diện nhầm, tìm lại trên toàn kho.
            if len(scoped) >= min(3, n):
                return [p for p, _ in scoped][:n]
        # Chroma lọc course_id phía máy chủ.
        dense = self.store.search(collection, vector, n, course_id=course_id)
        return [p for p, _ in dense][:n]

    def rerank(self, query: str, payloads: list[dict], top_k: int) -> list[Hit]:
        if not payloads:
            return []
        # Cho cross-encoder xem `text` thuần, không xem prefix: prefix là công cụ
        # hỗ trợ truy xuất, còn ở đây ta hỏi "đoạn văn này có trả lời được câu
        # hỏi không", và tiêu đề tài liệu không tham gia vào câu trả lời đó.
        scores = self.models.rerank_scores([(query, p.get("text", "")) for p in payloads])
        order = np.argsort(-scores)[:top_k]
        return [Hit(payloads[i], float(scores[i]), rank) for rank, i in enumerate(order)]

    def retrieve(
        self,
        query: str,
        collection: str,
        *,
        top_k: int | None = None,
        n_candidates: int | None = None,
        course_id: str | None = None,
    ) -> list[Hit]:
        top_k = top_k or self.settings.final_k
        n_candidates = n_candidates or self.settings.candidates_k
        return self.rerank(query, self.candidates(query, collection, n_candidates, course_id), top_k)

    def confidence(self, hits: list[Hit]) -> float:
        """Độ tin cậy = điểm cross-encoder cao nhất trong các đoạn truy xuất được.

        Lấy max chứ không lấy trung bình: câu hỏi chỉ cần **một** đoạn văn trả
        lời được. Trung bình sẽ phạt những truy vấn có đúng một đoạn hoàn hảo kèm
        bốn đoạn không liên quan — mà đó lại chính là hình dạng của một lần truy
        xuất thành công cho câu hỏi hẹp.
        """
        return max((h.score for h in hits), default=0.0)
