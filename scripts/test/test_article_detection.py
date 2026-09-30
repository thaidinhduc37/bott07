"""Kiểm thử hồi quy: dò số điều trong quy chế (nhãn trích dẫn "Điều N").

Lỗi đã gặp (29/09/2026): quy chế dạng Markdown có mục lục "Điều 1 … Điều 41" ở
đầu và tiêu đề thật dạng "## Điều 27." — mọi đoạn bị gắn nhãn "Điều 41". Không
cần API hay DB.

    python scripts/test/test_article_detection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

from app.pipeline.ingestion import find_articles  # noqa: E402

failed = 0


def check(name: str, got, want) -> None:
    global failed
    ok = got == want
    failed += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        có: {got}\n        cần: {want}"))


def labels(text: str) -> list[str]:
    return [label for _, label in find_articles(text)]


def line_of(text: str, label: str) -> int:
    pos = dict((lbl, p) for p, lbl in find_articles(text))[label]
    return text.count("\n", 0, pos) + 1


toc_md = (
    "# MỤC LỤC\n\nĐiều 1. Phạm vi điều chỉnh 3\n\nĐiều 2. Chương trình đào tạo 3\n\nĐiều 3. Học phần 5\n\n"
    "# QUY CHẾ\n\n## Điều 1. Phạm vi điều chỉnh\nNội dung.\n\n## Điều 2. Chương trình đào tạo\n"
    "Theo Điều 1 của Quy chế này.\n\n## Điều 3. Học phần\nNội dung.\n"
)
check("Markdown có mục lục: đủ 3 điều", labels(toc_md), ["Điều 1", "Điều 2", "Điều 3"])
check("Markdown có mục lục: Điều 2 nhận tại tiêu đề thật (dòng 14), không phải mục lục",
      line_of(toc_md, "Điều 2"), 14)

legacy = "Điều 1. Phạm vi\nnội dung\nĐiều 2. Đối tượng\nTheo Điều 1 của Quy chế này\nĐiều 3. Thang điểm 10\nĐiều 4. Hiệu lực"
check("Văn bản kiểu PDF (không mục lục), tiêu đề kết thúc bằng số vẫn giữ",
      labels(legacy), ["Điều 1", "Điều 2", "Điều 3", "Điều 4"])
check("Tiêu đề in đậm", labels("**Điều 1.** Phạm vi áp dụng\nabc\n**Điều 2.** Đối tượng áp dụng"), ["Điều 1", "Điều 2"])
check("Tham chiếu chéo không thành tiêu đề", labels("Điều 5. Học phí\nĐiều 2 nêu trên quy định\nĐiều 6. Hiệu lực"), ["Điều 5", "Điều 6"])

real = ROOT / "copus" / "quyche" / "QuyCheDaoTaoDanSu_Trinh_ky.md"
if real.exists():
    text = real.read_text(encoding="utf-8")
    found = find_articles(text)
    check("Quy chế đào tạo dân sự: 41 điều", len(found), 41)
    check("Quy chế đào tạo dân sự: mọi điều nhận tại dòng '## Điều'",
          all(text.splitlines()[text.count("\n", 0, p)].startswith("## Điều") for p, _ in found), True)

print(f"\n{'Đạt' if not failed else f'{failed} lỗi'}")
sys.exit(1 if failed else 0)
