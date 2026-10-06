"""Vòng lặp truy xuất phải báo cáo vòng TỐT NHẤT, không phải vòng cuối.

Bối cảnh. Vòng lặp retrieve → grade → rewrite (§18) viết lại truy vấn khi bằng
chứng chưa đủ. Viết lại là một phỏng đoán, và phỏng đoán có lúc sai. Quan sát
thật trên câu "Sinh viên bị cảnh báo học tập trong trường hợp nào?":

    round1:retrieved=5,conf=0.361     ← gấp mười hai lần τ = 0.030
    grade=insufficient
    rewrite->Quy chế đào tạo đại học chính quy -
    round2:retrieved=5,conf=0.006     ← bản viết lại tệ hơn hẳn
    gate=below_threshold
    ABSTAIN  "Độ tin cậy truy xuất 0.006 dưới ngưỡng 0.030"

Câu cuối cùng nói dối. Truy xuất **tốt nhất** không hề dưới ngưỡng — chỉ có lần
đoán cuối là dưới. Người vận hành đọc thông báo đó sẽ đi chỉnh tầng truy xuất
hoặc hạ τ, trong khi thứ hỏng là bước viết lại.

Bài kiểm thử này chạy orchestrator thật với retriever và reader giả, nên nó đo
đúng logic vòng lặp mà không cần Qdrant, không cần mô hình, không tốn hạn mức.

    python scripts/test/test_vong_tot_nhat.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import Settings  # noqa: E402
from app.pipeline.orchestrator import Orchestrator  # noqa: E402
from app.pipeline.retrieval import Hit  # noqa: E402

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


class FakeRetriever:
    """Trả về độ tin cậy đã định sẵn cho từng vòng, theo thứ tự."""

    def __init__(self, confidences: list[float]):
        self._confidences = confidences
        self._round = 0

    def candidates(self, query, collection, k, course_id=None):
        return [{"document_id": "d1", "chunk_id": f"c{self._round}", "text": "…"}]

    def rerank(self, question, candidates, top_k):
        # Mỗi lần rerank là một vòng mới. Trả về hit mang nhãn vòng để bài kiểm
        # thử phân biệt được vòng nào thắng.
        idx = min(self._round, len(self._confidences) - 1)
        self._round += 1
        return [
            Hit(
                payload={
                    "chunk_id": f"round{idx + 1}",
                    "text": f"Nội dung giả của vòng {idx + 1}.",
                    "document_title": "Quy chế học tập",
                },
                score=self._confidences[idx],
                rank=1,
            )
        ]

    def confidence(self, hits):
        return hits[0].score if hits else 0.0


class FakeReader:
    """Chấm luôn là 'chưa đủ' để ép vòng lặp viết lại rồi chạy hết số vòng."""

    provider = "fake"
    model = "fake-model"

    class _Usage:
        def __init__(self):
            self.calls = {}

    def __init__(self):
        self.usage = self._Usage()
        self.usage.calls = __import__("collections").Counter()

    @property
    def available(self):
        return True

    async def chat(self, prompt, **kwargs):
        self.usage.calls[kwargs.get("tag", "misc")] += 1
        tag = kwargs.get("tag", "")
        if tag == "route":
            return "SIMPLE"
        if tag == "rewrite":
            return "một bản viết lại tệ hơn"
        return "…"

    async def yes_no(self, question, *, tag="judge"):
        self.usage.calls[tag] += 1
        return False  # luôn "chưa đủ căn cứ"


async def run_case(name: str, confidences: list[float]) -> dict:
    settings = Settings()
    settings.max_retrieval_rounds = len(confidences)
    orch = Orchestrator(FakeRetriever(confidences), FakeReader(), settings)
    res = await orch.answer(question="câu hỏi thử", collection="sa_quyche", tau=0.030)
    print(f"\n--- {name} ---")
    for step in res.trace:
        print(f"    {step}")
    return {
        "confidence": res.confidence,
        "hits": res.hits,
        "abstained": res.abstained,
        "reason": res.abstain_reason,
        "trace": res.trace,
    }


async def main() -> int:
    # Trường hợp thật đã quan sát được: vòng 2 tệ hơn hẳn vòng 1.
    r = await run_case("vòng 2 tệ hơn vòng 1", [0.361, 0.006])

    check(
        "báo cáo độ tin cậy của vòng TỐT NHẤT chứ không phải vòng cuối",
        abs(r["confidence"] - 0.361) < 1e-9,
        f"nhận được {r['confidence']}",
    )
    check(
        "giữ lại đoạn văn của vòng tốt nhất",
        bool(r["hits"]) and r["hits"][0].payload["chunk_id"] == "round1",
        f"nhận được {r['hits']}",
    )
    check(
        "trace ghi rõ đã lùi về vòng nào",
        any("fallback->round1" in s for s in r["trace"]),
    )
    check(
        "vẫn từ chối — lùi về vòng tốt nhất KHÔNG được biến thành câu trả lời",
        r["abstained"],
    )
    check(
        "lý do từ chối là thiếu căn cứ, không phải đổ lỗi cho truy xuất",
        "căn cứ" in r["reason"],
        r["reason"],
    )

    # Vòng 2 tốt hơn: không được lùi, vì vòng cuối đã là vòng tốt nhất.
    r2 = await run_case("vòng 2 tốt hơn vòng 1", [0.100, 0.500])
    check(
        "vòng cuối tốt hơn thì không lùi",
        abs(r2["confidence"] - 0.500) < 1e-9 and not any("fallback" in s for s in r2["trace"]),
        f"conf={r2['confidence']}",
    )

    # Chỉ một vòng: không có gì để so, và không được thêm bước lùi thừa.
    r3 = await run_case("chỉ một vòng", [0.200])
    check(
        "một vòng thì không có bước lùi",
        not any("fallback" in s for s in r3["trace"]),
    )

    print(f"\n{PASSED}/{PASSED + FAILED} kiểm tra đạt")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
