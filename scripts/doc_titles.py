"""Tên hiển thị (có dấu) của giáo trình / đề cương, lấy từ chính nội dung tệp.

Trước đây tên tài liệu suy ra từ TÊN TỆP ("33_Co_so_du_lieu.md" -> "Co so du lieu")
nên mất hết dấu tiếng Việt, kéo theo tên hiển thị ở trang tài liệu, kế hoạch ôn
thi và cả trích dẫn của trợ lý. Mọi đề cương chi tiết học phần đều có dòng
"- Tên học phần: Cơ sở dữ liệu" viết đúng dấu — dùng nó làm nguồn.

Dùng chung cho các script nạp (`ingest_*.py`) và `fix_document_titles.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

_NAME_RE = re.compile(r"Tên học phần\s*:\s*(.+)")

# Giáo trình (không phải đề cương) không có dòng "Tên học phần".
_BOOKS = {
    "1.giao_trinh_triet_hoc_mac_lenin.md": "Giáo trình Triết học Mác - Lênin",
    "2.giao_trinh_kinh_te_chinh_tri_mac_lenin.md": "Giáo trình Kinh tế chính trị Mác - Lênin",
    "4.giao_trinh_tu_tuong_ho_chi_minh.md": "Giáo trình Tư tưởng Hồ Chí Minh",
    "5.giao_trinh_lich_su_dang_cong_san_viet_nam.md": "Giáo trình Lịch sử Đảng Cộng sản Việt Nam",
}

# Hai đề cương cùng tên học phần nhưng khác nội dung — thêm phần phân biệt để danh
# sách tài liệu và trích dẫn không có hai dòng giống hệt nhau.
_DISAMBIGUATE = {
    "22_K5_Giao_duc_TC3_Bong_ban.md": "Giáo dục thể chất (HP3) — Bóng bàn",
    "23_K5_Giao_duc_TC3_Cau_long.md": "Giáo dục thể chất (HP3) — Cầu lông",
}

# Tài liệu nạp thủ công, tên gõ không dấu.
KNOWN_FIXES = {
    "Quy che hoc tap": "Quy chế học tập",
}


def title_from_outline(text: str) -> str | None:
    """Tên học phần trong 60 dòng đầu của đề cương, bỏ dấu chấm cuối câu."""
    head = "\n".join(text.splitlines()[:60])
    m = _NAME_RE.search(head)
    if not m:
        return None
    return m.group(1).strip().rstrip(".").strip() or None


def _fallback(filename: str) -> str:
    """'33_Co_so_du_lieu.md' -> 'Co so du lieu' (không dấu — chỉ khi không có nguồn nào khác)."""
    stem = Path(filename).stem
    if "_" in stem:
        stem = stem.split("_", 1)[1]
    return stem.replace("_", " ").strip()


def display_title(filename: str, text: str | None = None, corpus_dir: Path | None = None) -> str:
    """Tên hiển thị của tệp `filename`. `text` (nội dung) ưu tiên; không có thì đọc
    từ `corpus_dir/filename`; không đọc được thì trả tên suy ra từ tên tệp."""
    name = Path(filename).name
    if name in _DISAMBIGUATE:
        return _DISAMBIGUATE[name]
    if name in _BOOKS:
        return _BOOKS[name]
    if text is None and corpus_dir is not None:
        p = corpus_dir / name
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="replace")
    if text:
        found = title_from_outline(text)
        if found:
            return found
    return _fallback(name)
