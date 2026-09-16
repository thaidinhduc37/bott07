"""Client bỏ đi thì máy chủ phải ngừng tính.

Bối cảnh. Ngày 10/08/2026, sau khi đã sửa lỗi chặn event loop, vẫn quan sát được
điều này: NestJS hết giờ và ngắt kết nối, PostgreSQL ghi FAILED, nhưng
rag-service **không hề biết** và tính tiếp. Một lần nạp bị bỏ vẫn chạy thêm 30
phút ở 674% CPU cho một kết quả không ai nhận. Người dùng bấm "thử lại", và mỗi
lần bấm lại xếp thêm một việc như thế vào hàng đợi.

Vì sao lỗi này chỉ sửa được *sau* khi đã chia lô: Python không giết được một
luồng đang chạy. Hủy một `run_in_executor` không dừng được lời gọi torch đang
dở. Thứ hủy được là **lần gọi tiếp theo**. Nên nếu cả tài liệu nằm trong một lời
gọi encode duy nhất thì không có "lần tiếp theo" nào để hủy, và hủy trở thành vô
nghĩa. Chia lô là thứ biến việc hủy từ ý định thành hiệu lực: chậm nhất một lô
sau khi client bỏ đi, máy chủ dừng.

    python scripts/test/test_huy_khi_client_bo_di.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server" / "rag-service"))

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

from app.cancellation import ClientDisconnected, run_until_disconnect  # noqa: E402
from app.pipeline import blocking  # noqa: E402

PASSED = 0
FAILED = 0

SO_LO = 20
LO_S = 0.05


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ĐẠT  {name}")
    else:
        FAILED += 1
        print(f"  TRƯỢT {name}" + (f" — {detail}" if detail else ""))


class RequestGia:
    """Request giả: báo còn kết nối vài lần rồi báo client đã bỏ đi."""

    def __init__(self, so_lan_con_song: int):
        self.so_lan_con_song = so_lan_con_song
        self.so_lan_hoi = 0

    async def is_disconnected(self) -> bool:
        self.so_lan_hoi += 1
        return self.so_lan_hoi > self.so_lan_con_song


class ViecNap:
    """Việc nạp giả, chia lô đúng như `IndexingService.ingest` thật."""

    def __init__(self) -> None:
        self.lo_da_xong = 0

    async def chay(self) -> str:
        for _ in range(SO_LO):
            await blocking.run(time.sleep, LO_S)
            self.lo_da_xong += 1
        return "nap xong"


async def main() -> int:
    # --- 1. Client ở lại: việc phải chạy trọn vẹn --------------------------
    # Kiểm tra này giữ cho bản sửa không "hủy nhầm" mọi thứ.
    viec = ViecNap()
    ket_qua = await run_until_disconnect(RequestGia(10_000), viec.chay(), poll_s=0.01)
    check(
        "client ở lại thì việc chạy hết và trả về kết quả",
        ket_qua == "nap xong" and viec.lo_da_xong == SO_LO,
        f"lô xong {viec.lo_da_xong}/{SO_LO}, kết quả {ket_qua!r}",
    )

    # --- 2. Client bỏ đi: việc phải dừng ----------------------------------
    viec = ViecNap()
    req = RequestGia(3)  # còn sống 3 lần hỏi, sau đó coi như đã ngắt
    t0 = time.time()
    try:
        await run_until_disconnect(req, viec.chay(), poll_s=0.01)
        bao_loi = False
    except ClientDisconnected:
        bao_loi = True
    mat = time.time() - t0

    check(
        "client bỏ đi thì báo ClientDisconnected chứ không âm thầm trả kết quả",
        bao_loi,
    )
    check(
        "việc dừng lại thay vì chạy nốt",
        viec.lo_da_xong < SO_LO,
        f"vẫn chạy hết {viec.lo_da_xong}/{SO_LO} lô",
    )
    check(
        "dừng sớm, không đợi hết toàn bộ việc",
        mat < SO_LO * LO_S * 0.6,
        f"mất {mat:.2f}s, cả việc là {SO_LO * LO_S:.2f}s",
    )

    # --- 3. Dừng trong vòng một lô ----------------------------------------
    # Đây là điều chia lô mua được. Không đòi dừng tức thì — lời gọi torch đang
    # dở không giết được — chỉ đòi không tràn sang lô thứ hai.
    lo_luc_huy = viec.lo_da_xong
    await asyncio.sleep(LO_S * 4)
    check(
        "sau khi hủy thì không có lô nào chạy thêm",
        viec.lo_da_xong == lo_luc_huy,
        f"chạy thêm {viec.lo_da_xong - lo_luc_huy} lô sau khi đã hủy",
    )

    print(f"\n{PASSED}/{PASSED + FAILED} kiểm tra đạt")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
