"""Việc nặng CPU không được chạy trên event loop.

Bối cảnh. Ngày 10/08/2026, dịch vụ RAG "chết" mà tiến trình vẫn sống: cổng 8000
vẫn nghe, nhưng `/health` hết giờ sau 15 giây và mọi truy vấn treo. py-spy chỉ
đúng chỗ:

    Thread MainThread (active):
        forward (sentence_transformers/models/Transformer.py:393)
        encode  (app/pipeline/models.py:118)
        ingest  (app/pipeline/indexing.py:184)
        ingest  (app/routers/rag.py:30)
        run_forever (asyncio/base_events.py:608)

Một lệnh nạp tài liệu đang nhúng bằng BGE-M3 **ngay trên MainThread**, tức trên
chính event loop của asyncio. Trong suốt thời gian đó không handler nào khác
chạy được — kể cả `/health`. NestJS hết giờ ở giây 120 rồi ngắt kết nối, nhưng
máy chủ không hề biết và vẫn tính tiếp; kết nối nằm lại ở CLOSE_WAIT còn người
dùng bấm thử lại, xếp thêm việc vào hàng đợi. Tám kết nối CLOSE_WAIT và 45 phút
CPU liên tục là kết quả.

Điều làm lỗi này khó thấy: `ModelRegistry` đã được viết cho đúng mô hình threadpool
— nó có sẵn một `threading.Lock` với ghi chú "Uvicorn chạy handler đồng bộ trong
threadpool". Ý đồ thiết kế là đúng; chỉ có route viết `async def` là phá vỡ nó,
vì `async def` giữ nguyên thân hàm trên event loop thay vì đẩy sang threadpool.

Bài kiểm thử này đo đúng tính chất cần giữ: **trong lúc một việc nặng CPU đang
chạy, event loop vẫn phải phục vụ được việc khác.** Nó chạy orchestrator thật với
retriever giả có chèn `time.sleep`, nên không cần Qdrant, không cần mô hình,
không tốn hạn mức.

    python scripts/test/test_khong_chan_event_loop.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server" / "rag-service"))

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

from app.config import Settings  # noqa: E402
from app.pipeline import blocking  # noqa: E402
from app.pipeline.orchestrator import Orchestrator  # noqa: E402
from app.pipeline.retrieval import Hit  # noqa: E402

PASSED = 0
FAILED = 0

# Việc nặng giả lập kéo dài bao lâu, và nhịp tim đập mỗi bao lâu. Nếu event loop
# rảnh thì nhịp tim đập được khoảng BLOCK_S / TICK_S lần.
BLOCK_S = 1.0
TICK_S = 0.02
# Ngưỡng rộng tay: chỉ cần loop sống, không đòi đủ số nhịp lý thuyết.
MIN_TICKS = 20


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ĐẠT  {name}")
    else:
        FAILED += 1
        print(f"  TRƯỢT {name}" + (f" — {detail}" if detail else ""))


class NhipTim:
    """Đếm số lần event loop quay lại được với ta.

    Đây là phép đo trực tiếp thứ `/health` cần: một coroutine nhỏ, không làm gì
    ngoài việc thức dậy đúng hẹn. Nó không đập được nghĩa là `/health` cũng
    không được phục vụ.
    """

    def __init__(self) -> None:
        self.ticks = 0
        self._task: asyncio.Task | None = None

    async def _dap(self) -> None:
        while True:
            await asyncio.sleep(TICK_S)
            self.ticks += 1

    def bat_dau(self) -> None:
        self._task = asyncio.create_task(self._dap())

    async def dung(self) -> int:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return self.ticks


class RetrieverChan:
    """Retriever giả, chèn `time.sleep` đúng chỗ torch thật sẽ chiếm CPU.

    `time.sleep` mô phỏng trung thực hơn `asyncio.sleep` ở đây: cả hai đều chờ,
    nhưng chỉ `time.sleep` giữ luồng lại — và giữ luồng chính là điều torch làm.
    """

    def candidates(self, query, collection, k, course_id=None):
        time.sleep(BLOCK_S / 2)
        return [{"document_id": "d1", "chunk_id": "c1", "text": "…"}]

    def rerank(self, question, candidates, top_k):
        time.sleep(BLOCK_S / 2)
        return [
            Hit(
                payload={
                    "chunk_id": "c1",
                    "text": "Nội dung giả.",
                    "document_title": "Quy chế học tập",
                },
                score=0.9,
                rank=1,
            )
        ]

    def confidence(self, hits):
        return hits[0].score if hits else 0.0


class ReaderNhanh:
    """Reader giả trả lời tức thì — bài kiểm thử này không đo LLM."""

    provider = "fake"
    model = "fake-model"

    class _Usage:
        def __init__(self):
            import collections

            self.calls = collections.Counter()

    def __init__(self):
        self.usage = self._Usage()

    @property
    def available(self):
        return True

    async def chat(self, prompt, **kwargs):
        self.usage.calls[kwargs.get("tag", "misc")] += 1
        return "SIMPLE" if kwargs.get("tag") == "route" else "Câu trả lời giả [1]."

    async def yes_no(self, question, *, tag="judge"):
        self.usage.calls[tag] += 1
        return True  # đủ căn cứ → không viết lại, chỉ một vòng


async def do_nhip_khi_chay(coro) -> tuple[int, float]:
    """Chạy `coro` và đếm số nhịp tim đập được trong lúc nó chạy."""
    tim = NhipTim()
    tim.bat_dau()
    await asyncio.sleep(0)  # cho nhịp tim kịp vào loop trước khi việc nặng bắt đầu
    t0 = time.time()
    await coro
    elapsed = time.time() - t0
    return await tim.dung(), elapsed


async def main() -> int:
    # --- 1. Cơ chế nền: helper đẩy việc nặng sang luồng riêng ---------------
    ticks, elapsed = await do_nhip_khi_chay(blocking.run(time.sleep, BLOCK_S))
    check(
        "blocking.run giữ event loop rảnh trong lúc việc nặng chạy",
        ticks >= MIN_TICKS,
        f"chỉ đập được {ticks} nhịp trong {elapsed:.2f}s (cần ≥ {MIN_TICKS})",
    )

    # --- 2. Đường đi thật của một truy vấn ----------------------------------
    # Đây là hồi quy cho chính sự cố: rerank và nhúng truy vấn nằm trong
    # orchestrator, và orchestrator được gọi từ handler async.
    settings = Settings()
    settings.max_retrieval_rounds = 1
    orch = Orchestrator(RetrieverChan(), ReaderNhanh(), settings)

    ticks, elapsed = await do_nhip_khi_chay(
        orch.answer(question="câu hỏi thử", collection="sa_quyche", tau=0.030)
    )
    check(
        "orchestrator.answer không chặn event loop khi xếp hạng",
        ticks >= MIN_TICKS,
        f"chỉ đập được {ticks} nhịp trong {elapsed:.2f}s (cần ≥ {MIN_TICKS})",
    )

    # --- 3. Việc nặng phải được tuần tự hóa ---------------------------------
    # Đẩy sang luồng khác mà thả cho chạy song song tùy ý thì đổi một lỗi lấy
    # một lỗi khác: hai lần suy luận cùng lúc nhân đôi RAM đỉnh và tranh nhau
    # lõi CPU trên máy 16 GB không GPU. Một luồng worker duy nhất giữ nguyên
    # con số 1.83 GB mà README công bố.
    dang_chay = 0
    dinh = 0

    def viec_nang():
        nonlocal dang_chay, dinh
        dang_chay += 1
        dinh = max(dinh, dang_chay)
        time.sleep(0.2)
        dang_chay -= 1

    await asyncio.gather(*(blocking.run(viec_nang) for _ in range(4)))
    check(
        "bốn việc nặng cùng lúc vẫn chỉ chạy một lần một",
        dinh == 1,
        f"có lúc {dinh} việc chạy song song",
    )

    # --- 4. Việc nạp dài phải chia lô -------------------------------------
    # Vì sao đây là một phép kiểm riêng: đẩy việc nặng sang luồng worker mới
    # chỉ cứu được event loop. Luồng worker vẫn chỉ có một, nên nếu lệnh nạp
    # gọi encode **một lần** cho cả tài liệu thì nó giữ worker suốt mười phút
    # và mọi truy vấn của học viên vẫn hết giờ ở giây 120 — đúng triệu chứng
    # cũ, chỉ đổi chỗ. Chia lô là thứ biến "chờ hết cả lần nạp" thành "chờ hết
    # một lô".
    #
    # Đo bằng cách chạy một việc nạp giả chia lô, rồi chen một truy vấn giả vào
    # giữa và xem nó phải chờ bao lâu.
    SO_LO, LO_S = 10, 0.1  # việc nạp: 10 lô, tổng 1.0s
    async def nap_chia_lo():
        for _ in range(SO_LO):
            await blocking.run(time.sleep, LO_S)

    async def truy_van_chen_ngang() -> float:
        await asyncio.sleep(LO_S * 2.5)  # để việc nạp chạy được vài lô
        t = time.time()
        await blocking.run(time.sleep, 0.01)
        return time.time() - t

    _, cho = await asyncio.gather(nap_chia_lo(), truy_van_chen_ngang())
    check(
        "truy vấn chen giữa lần nạp chỉ chờ hết một lô, không chờ hết cả lần nạp",
        cho < LO_S * 3,
        f"phải chờ {cho:.2f}s — một lô là {LO_S}s, cả lần nạp là {SO_LO * LO_S}s",
    )

    print(f"\n{PASSED}/{PASSED + FAILED} kiểm tra đạt")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
