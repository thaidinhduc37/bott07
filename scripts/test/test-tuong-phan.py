"""Đo tương phản màu của giao diện theo WCAG 2.1, cho cả hai chế độ sáng và tối.

Vì sao là một bài kiểm thử chứ không phải một lần kiểm tra: màu được sửa bằng
mắt. Mắt thích nghi rất nhanh với màn hình đang ngồi trước mặt, nên "trông ổn"
là bằng chứng về màn hình của người sửa chứ không phải về màu. Lỗi tìm ra khi
viết bài kiểm thử này là một ví dụ đúng kiểu: `--ink-faint` ở 2.61 : 1 đã nằm
trong giao diện suốt và không ai thấy vấn đề gì.

Kịch bản này đọc **thẳng từ `globals.css`**, không chép lại giá trị màu. Chép
lại thì bài kiểm thử sẽ đo bản sao chứ không đo thứ người dùng nhìn thấy, và nó
sẽ vẫn xanh sau khi ai đó đổi màu trong CSS.

    python scripts/test/test-tuong-phan.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

CSS = Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "app" / "globals.css"

# Ngưỡng WCAG 2.1 AA.
AA_NORMAL = 4.5   # chữ dưới 18.66px thường / 24px
AA_LARGE = 3.0    # chữ lớn, và ranh giới của thành phần giao diện
NON_TEXT = 1.5    # đường kẻ trang trí — không phải yêu cầu của WCAG, là sàn tự đặt


# --------------------------------------------------------------------- màu sắc


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# --------------------------------------------------------------- đọc token


_TOKEN_RE = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", re.MULTILINE)
_DARK_RE = re.compile(
    r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{(.*?)\n\}", re.DOTALL
)


def read_themes(css: str) -> tuple[dict[str, str], dict[str, str]]:
    """Trả (sáng, tối). Chế độ tối kế thừa chế độ sáng rồi ghi đè."""
    dark_match = _DARK_RE.search(css)
    dark_block = dark_match.group(1) if dark_match else ""
    # Bỏ khối tối ra khỏi phần sáng, nếu không token tối sẽ ghi đè token sáng.
    light_source = css.replace(dark_block, "") if dark_block else css

    light = dict(_TOKEN_RE.findall(light_source))
    dark = dict(light)
    dark.update(dict(_TOKEN_RE.findall(dark_block)))
    return light, dark


# --------------------------------------------------------------- các phép đo

# (mô tả, token chữ, token nền, ngưỡng)
#
# Mỗi dòng ứng với một cặp thật sự xuất hiện trong giao diện. Thêm dòng khi thêm
# một cặp màu mới; đừng thêm dòng chỉ vì hai token tồn tại.
CHECKS: list[tuple[str, str, str, float]] = [
    ("chữ chính trên giấy",       "--ink",       "--sheet",      AA_NORMAL),
    ("chữ chính trên nền trang",  "--ink",       "--paper",      AA_NORMAL),
    ("chú thích trên giấy",       "--ink-soft",  "--sheet",      AA_NORMAL),
    ("chú thích trên nền trang",  "--ink-soft",  "--paper",      AA_NORMAL),
    # `eyebrow` cỡ 11px dùng token này — là chữ nhỏ, nên ngưỡng là 4.5 chứ
    # không phải 3.0.
    ("nhãn nhỏ, siêu dữ liệu",    "--ink-faint", "--sheet",      AA_NORMAL),
    ("liên kết trên giấy",        "--pen",       "--sheet",      AA_NORMAL),
    ("chữ trên nút chính",        "--on-pen",    "--pen",        AA_NORMAL),
    ("chữ trên nút nguy hiểm",    "--on-pen",    "--seal",       AA_NORMAL),
    ("thông báo lỗi",             "--seal-ink",  "--seal-wash",  AA_NORMAL),
    ("thông báo thông tin",       "--pen-ink",   "--pen-wash",   AA_NORMAL),
    ("thông báo thành công",      "--ok-ink",    "--ok-wash",    AA_NORMAL),
    ("thông báo cảnh báo",        "--warn-ink",  "--warn-wash",  AA_NORMAL),
    ("nhãn trạng thái tốt",       "--ok",        "--ok-wash",    AA_NORMAL),
    ("nhãn trạng thái cảnh báo",  "--warn",      "--warn-wash",  AA_NORMAL),
    ("nhãn dấu đỏ",               "--seal",      "--seal-wash",  AA_NORMAL),
    ("viền ô nhập khi focus",     "--pen",       "--paper",      AA_LARGE),
    ("đường kẻ mảnh trên giấy",   "--rule",      "--sheet",      NON_TEXT),
    # Mặt lõm: nền của đầu bảng, ô nhập, khối trích dẫn và chip. Ba mức mực đều
    # xuất hiện trên nó, nên đo cả ba — một mặt phẳng mới là một mặt phẳng mới,
    # không phải một biến thể nhỏ của mặt giấy.
    ("chữ chính trên mặt lõm",    "--ink",       "--sheet-2",    AA_NORMAL),
    ("chú thích trên mặt lõm",    "--ink-soft",  "--sheet-2",    AA_NORMAL),
    ("nhãn nhỏ trên mặt lõm",     "--ink-faint", "--sheet-2",    AA_NORMAL),
]

# Mặt bảng ký cố ý không theo chế độ tối — kiểm riêng, luôn dùng giá trị của
# chế độ sáng.
SIGNATURE_CHECK = ("nét ký trên mặt bảng ký", "--signature-ink", "--signature-surface", AA_NORMAL)

# Phép đo chỉ áp cho chế độ tối.
#
# Ở chế độ sáng, mép thẻ được vẽ bằng bóng đổ và `--rule-faint` chỉ là nét phụ —
# đo nó ở chế độ sáng sẽ trượt, và trượt đúng theo thiết kế. Ở chế độ tối bóng đổ
# gần như không đọc được, nên nét này gánh toàn bộ việc tách thẻ khỏi nền và phải
# thật sự nhìn thấy. Cùng một token, hai vai trò khác nhau, nên hai ngưỡng.
DARK_ONLY_CHECKS: list[tuple[str, str, str, float]] = [
    ("mép thẻ trên giấy (tối)",   "--rule-faint", "--sheet",     NON_TEXT),
]


def main() -> int:
    if not CSS.exists():
        print(f"Không thấy {CSS}")
        return 2

    css = CSS.read_text(encoding="utf-8")
    light, dark = read_themes(css)

    failures = 0
    total = 0

    for theme_name, tokens in (("SÁNG", light), ("TỐI", dark)):
        print(f"\n=== CHẾ ĐỘ {theme_name} ===")
        for desc, fg_tok, bg_tok, need in CHECKS:
            if fg_tok not in tokens or bg_tok not in tokens:
                print(f"  THIẾU {desc:<26} — không thấy {fg_tok} hoặc {bg_tok}")
                failures += 1
                total += 1
                continue
            total += 1
            r = contrast(tokens[fg_tok], tokens[bg_tok])
            passed = r >= need
            if not passed:
                failures += 1
            mark = "ĐẠT " if passed else "TRƯỢT"
            print(f"  {mark} {desc:<26} {r:5.2f}:1  (cần {need})")

        if theme_name != "TỐI":
            continue
        for desc, fg_tok, bg_tok, need in DARK_ONLY_CHECKS:
            total += 1
            r = contrast(tokens[fg_tok], tokens[bg_tok])
            passed = r >= need
            if not passed:
                failures += 1
            print(f"  {'ĐẠT ' if passed else 'TRƯỢT'} {desc:<26} {r:5.2f}:1  (cần {need})")

    # Bảng ký: một phép đo, không nhân đôi theo chế độ.
    desc, fg_tok, bg_tok, need = SIGNATURE_CHECK
    print("\n=== KHÔNG THEO CHẾ ĐỘ ===")
    total += 1
    r = contrast(light[fg_tok], light[bg_tok])
    passed = r >= need
    if not passed:
        failures += 1
    print(f"  {'ĐẠT ' if passed else 'TRƯỢT'} {desc:<26} {r:5.2f}:1  (cần {need})")
    if bg_tok in dark and dark[bg_tok] != light[bg_tok]:
        print(f"  TRƯỢT {bg_tok} bị ghi đè ở chế độ tối — nét ký sẽ chìm vào nền")
        failures += 1
        total += 1

    print(f"\n{total - failures}/{total} phép đo đạt")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
