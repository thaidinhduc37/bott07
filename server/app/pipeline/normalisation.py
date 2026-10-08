"""§4 Chuẩn hóa: bỏ tiêu đề chạy, chân trang và số trang lặp ở gần mọi trang (nếu không chúng thành những đoạn văn hơi
giống mọi truy vấn và chiếm chỗ nội dung thật).

Nhận diện theo cấu trúc: dòng xuất hiện ở vùng đầu hoặc cuối của phần lớn số trang là boilerplate. Chốt an toàn: nếu việc
làm sạch xóa quá nửa corpus thì heuristic đã sai (rủi ro với tài liệu ngắn) và giữ nguyên văn bản gốc.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.pipeline.ingestion import Page

# Vùng đầu/cuối mỗi trang được xét, tính bằng số dòng.
ZONE_LINES = 2
# Tỷ lệ số trang mà một dòng phải xuất hiện để bị coi là boilerplate.
BOILERPLATE_THRESHOLD = 0.6
# Dòng dài hơn ngưỡng này là nội dung, không phải tiêu đề chạy.
MAX_BOILERPLATE_LEN = 120
# Giữ lại ít nhất bấy nhiêu phần văn bản, nếu không thì hủy kết quả làm sạch.
MIN_RETAINED_RATIO = 0.5


class NormalisationReport:
    def __init__(self) -> None:
        self.by_source: dict[str, dict] = {}
        self.rejected: bool = False
        self.chars_before: int = 0
        self.chars_after: int = 0

    def as_dict(self) -> dict:
        return {
            "rejected": self.rejected,
            "chars_before": self.chars_before,
            "chars_after": self.chars_after,
            "removed_ratio": (
                round(1 - self.chars_after / self.chars_before, 4) if self.chars_before else 0.0
            ),
            "by_source": self.by_source,
        }


def strip_boilerplate(pages: list[Page]) -> tuple[list[Page], NormalisationReport]:
    report = NormalisationReport()
    report.chars_before = sum(len(p.text) for p in pages)

    by_source: dict[str, list[Page]] = defaultdict(list)
    for p in pages:
        by_source[p.source].append(p)

    cleaned: list[Page] = []
    for source, group in by_source.items():
        counter: Counter[str] = Counter()
        for p in group:
            lines = [line.strip() for line in p.text.split("\n") if line.strip()]
            # Dùng set để một dòng lặp nhiều lần trong cùng một trang vẫn chỉ
            # tính một lần — nếu không, một trang có bảng lặp sẽ tự đẩy nội dung
            # của chính nó lên trên ngưỡng.
            zone = set(lines[:ZONE_LINES]) | set(lines[-ZONE_LINES:])
            for line in zone:
                if len(line) < MAX_BOILERPLATE_LEN:
                    counter[line] += 1

        # Sàn 3 trang: với tài liệu 2 trang thì "xuất hiện ở 60% số trang" là
        # một tiêu chí vô nghĩa.
        cutoff = max(3, int(BOILERPLATE_THRESHOLD * len(group)))
        boiler = {line for line, c in counter.items() if c >= cutoff}

        report.by_source[source] = {
            "pages": len(group),
            "boilerplate_lines": len(boiler),
            "examples": sorted(boiler, key=len, reverse=True)[:3],
        }

        for p in group:
            text = "\n".join(line for line in p.text.split("\n") if line.strip() not in boiler)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if text:
                cleaned.append(Page(p.source, p.page, text))

    cleaned.sort(key=lambda p: (p.source, p.page))
    report.chars_after = sum(len(p.text) for p in cleaned)

    if not cleaned or report.chars_after < MIN_RETAINED_RATIO * max(report.chars_before, 1):
        report.rejected = True
        report.chars_after = report.chars_before
        return pages, report

    return cleaned, report
