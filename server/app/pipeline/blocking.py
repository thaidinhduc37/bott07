"""Một luồng worker duy nhất cho mọi việc nặng CPU.

Vì sao cần tệp này. Handler của FastAPI viết `async def` chạy **trên chính event
loop**. Điều đó đúng với việc chờ mạng, nhưng sai với việc tính toán: một lệnh
nhúng BGE-M3 hay một lượt xếp hạng cross-encoder chiếm luồng hàng chục giây tới
hàng phút, và trong suốt thời gian đó không handler nào khác chạy được — kể cả
`/health`. Dịch vụ trông như đã chết trong khi nó chỉ đang bận.

Vì sao **một** luồng chứ không phải threadpool mặc định:

  * Đẩy sang luồng khác là để event loop rảnh, không phải để chạy nhiều lượt
    suy luận cùng lúc. Trên máy 16 GB không GPU, hai lượt song song nhân đôi RAM
    đỉnh và tranh nhau lõi, làm cả hai cùng chậm.
  * Tuần tự hóa ở đây không làm mất gì so với trước: trước đây mọi việc vốn đã
    nối đuôi nhau trên event loop. Khác biệt là bây giờ hàng đợi nằm ở worker,
    còn event loop vẫn trả lời được.

torch nhả GIL trong lúc tính, nên luồng worker thật sự chạy song song với event
loop chứ không chỉ xen kẽ.

Các script chạy một lần (`ingest_corpus.py`, `calibrate_tau.py`) vẫn gọi thẳng
phiên bản đồng bộ — chúng không có event loop nào để bảo vệ.
"""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# Một luồng, đặt tên để nó hiện rõ trong py-spy và trong trình gỡ lỗi. Lần sau
# có ai dump stack thì thấy ngay việc nặng đang ở đâu.
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-worker")


async def run(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Chạy `fn` trên luồng worker và trả quyền điều khiển lại cho event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool, functools.partial(fn, *args, **kwargs))


def shutdown(wait: bool = False) -> None:
    """Đóng worker lúc dịch vụ tắt."""
    _pool.shutdown(wait=wait, cancel_futures=not wait)
