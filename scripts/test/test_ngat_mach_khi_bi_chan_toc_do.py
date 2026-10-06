"""Bị chặn tốc độ một lần thì đừng khám phá lại ở mọi stage sau.

Bối cảnh. Ngày 12/08/2026, khi hạn mức Gemini cạn, một truy vấn kéo từ 37.7 giây
lên 89.8–105.9 giây. Phần chênh không nằm ở CPU.

Cơ chế: một lỗi 429 **không** khớp `_HARD_QUOTA_MARKERS` được coi là chặn tốc độ
tạm thời, nên `chat()` thử lại `max_retries + 1` lần với backoff 20s rồi 40s —
sáu mươi giây cho một stage. Hết lượt thì ném `LlmUnavailable` mà **không mở cầu
dao**. Mỗi truy vấn có bốn stage gọi LLM, nên stage sau lại trả đủ sáu mươi giây
để khám phá lại đúng điều stage trước vừa biết.

Chính tệp `llm.py` đã lập luận như vậy ở chỗ khác, cho trường hợp khóa sai:

    "một dòng .env gõ nhầm biến thành 36 lời gọi hỏng và hàng chục giây chờ —
     trong khi thông tin cần thiết đã có ngay từ lời gọi đầu tiên."

Nhánh chặn tốc độ thiếu đúng lập luận đó.

Cầu dao ngắn ≠ cầu dao hạn mức. Hết hạn mức theo ngày thì nghỉ 15 phút là hợp lý.
Bị chặn theo phút mà cũng nghỉ 15 phút là tự cấm mình dùng một khóa vẫn còn tốt.

    python scripts/test/test_ngat_mach_khi_bi_chan_toc_do.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

from app.pipeline.llm import BaseReader, LlmUnavailable  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ĐẠT  {name}")
    else:
        FAILED += 1
        print(f"  TRƯỢT {name}" + (f" — {detail}" if detail else ""))


class ReaderHong(BaseReader):
    """Reader giả luôn hỏng với một lỗi định sẵn.

    `max_retries=0` để bài kiểm thử không phải ngồi chờ backoff thật — thứ đang
    đo là *cầu dao có mở hay không*, không phải backoff dài bao nhiêu.
    """

    provider = "gia"

    def __init__(self, loi: str):
        super().__init__(model="gia-model", max_retries=0)
        self.loi = loi
        self.so_lan_goi = 0

    async def _generate(self, prompt, *, system=None, max_output_tokens=1024, temperature=0.0):
        self.so_lan_goi += 1
        raise RuntimeError(self.loi)


LOI_CHAN_TOC_DO = "429 RESOURCE_EXHAUSTED: too many requests, please retry"
LOI_HET_HAN_MUC = "429 You exceeded your current quota, check your plan and billing details"
LOI_LINH_TINH = "503 upstream connect error"


async def main() -> int:
    # --- 1. Chặn tốc độ: hết lượt thử thì phải mở cầu dao ------------------
    r = ReaderHong(LOI_CHAN_TOC_DO)
    try:
        await r.chat("xin chào", tag="grade")
    except LlmUnavailable:
        pass
    check(
        "hết lượt thử vì bị chặn tốc độ thì mở cầu dao",
        r.circuit_open,
        "cầu dao vẫn đóng — stage sau sẽ trả lại toàn bộ chi phí thử lại",
    )

    # --- 2. Stage sau không được gọi lại nhà cung cấp đang hỏng ------------
    # Đo bằng số lời gọi chứ không bằng đồng hồ: reader giả đặt `max_retries=0`
    # nên nó vốn đã nhanh, và một phép đo thời gian ở đây sẽ đạt kể cả khi bản
    # sửa chưa tồn tại. Số lời gọi mới là thứ phân biệt được.
    goi_truoc = r.so_lan_goi
    try:
        await r.chat("câu hỏi của stage sau", tag="generate")
    except LlmUnavailable:
        pass
    check(
        "stage sau không gọi lại nhà cung cấp đang hỏng",
        r.so_lan_goi == goi_truoc,
        f"gọi thêm {r.so_lan_goi - goi_truoc} lần — đó là toàn bộ chi phí thử lại trả lại lần nữa",
    )

    # --- 3. Cầu dao chặn-tốc-độ phải NGẮN ----------------------------------
    # Chặn theo phút mà nghỉ 15 phút là tự cấm mình dùng một khóa vẫn còn tốt.
    con_lai = r._breaker_open_until - time.monotonic()
    check(
        "cầu dao chặn tốc độ ngắn (≤ 5 phút), không dùng chung mức của hết hạn mức",
        0 < con_lai <= 300,
        f"còn {con_lai:.0f}s",
    )

    # --- 4. Hết hạn mức thật vẫn phải nghỉ dài (hồi quy) -------------------
    r2 = ReaderHong(LOI_HET_HAN_MUC)
    try:
        await r2.chat("xin chào", tag="generate")
    except LlmUnavailable:
        pass
    con_lai2 = r2._breaker_open_until - time.monotonic()
    check(
        "hết hạn mức thật vẫn mở cầu dao dài (> 5 phút)",
        con_lai2 > 300,
        f"còn {con_lai2:.0f}s",
    )

    # --- 5. Lỗi linh tinh KHÔNG được mở cầu dao (hồi quy) ------------------
    # Một lỗi mạng thoáng qua không phải lý do để cấm cả nhà cung cấp.
    r3 = ReaderHong(LOI_LINH_TINH)
    try:
        await r3.chat("xin chào", tag="grade")
    except LlmUnavailable:
        pass
    check(
        "lỗi thoáng qua không mở cầu dao",
        not r3.circuit_open,
        "một lỗi 503 đã cấm cả nhà cung cấp",
    )

    print(f"\n{PASSED}/{PASSED + FAILED} kiểm tra đạt")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
