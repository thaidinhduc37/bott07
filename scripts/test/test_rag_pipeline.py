"""Kiểm thử nghiệm thu dịch vụ RAG (Ngày 4).

Hai tiêu chí của kế hoạch:

  1. "10 câu hỏi thử đều trả về response đúng cấu trúc."
  2. "Câu trả lời không có nguồn phải ghi rõ chưa tìm thấy căn cứ, không tự bịa
     điều khoản."

Tiêu chí thứ hai là tiêu chí thật. Bất kỳ pipeline nào cũng vượt được tiêu chí
thứ nhất; chỉ pipeline có cổng abstention hoạt động mới vượt được tiêu chí thứ hai.
Vì vậy script kiểm tra riêng ba nhóm:

  * Câu trong phạm vi PHẢI được trả lời và PHẢI có trích dẫn.
  * Câu ngoài phạm vi PHẢI bị từ chối, và câu trả lời KHÔNG được chứa chuỗi
    "Điều <số>" — đó chính là hình dạng của một điều khoản bịa.
  * Trích dẫn PHẢI trỏ tới đúng điều/trang mà bộ dữ liệu kiểm thử ghi nhận.

    python scripts/test/test_rag_pipeline.py
    python scripts/test/test_rag_pipeline.py --no-llm   # chỉ kiểm phần truy xuất
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

# Console Windows mặc định là cp1252, không mã hóa nổi tiếng Việt. Không ép
# UTF-8 ở đây thì script chết ngay ở dòng in đầu tiên — một lỗi hiển thị bị
# hiểu nhầm thành lỗi pipeline.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = REPO_ROOT / "docs" / "testing" / "rag-eval-questions.json"

RAG_URL = os.environ.get("RAG_SERVICE_URL", "http://127.0.0.1:8000")
TOKEN = os.environ.get("RAG_INTERNAL_TOKEN", "change_me_internal_token")

REQUIRED_FIELDS = {
    "answer", "citations", "retrieved_chunks", "latency_ms",
    "abstained", "confidence", "threshold", "route", "rounds", "trace", "llm_calls",
}

# Hình dạng của một điều khoản bịa: "Điều 47" trong câu trả lời cho một câu hỏi
# mà corpus không có căn cứ.
ARTICLE_MENTION = re.compile(r"Điều\s+\d+")

passed = 0
failed = 0
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed, failed
    if ok:
        print(f"  \033[32mPASS\033[0m  {name}")
        passed += 1
    else:
        print(f"  \033[31mFAIL\033[0m  {name}  {detail}")
        failed += 1
        failures.append(f"{name} — {detail}")
    return ok


def query(client: httpx.Client, question: str, mode: str = "quyche", **kw) -> dict:
    r = client.post(
        f"{RAG_URL}/query",
        json={"question": question, "mode": mode, **kw},
        headers={"X-Internal-Token": TOKEN},
        timeout=300.0,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Bỏ qua các kiểm tra cần LLM; chỉ kiểm truy xuất, xếp hạng và cổng abstention.",
    )
    parser.add_argument("--mode", choices=["quyche", "giaotrinh"], default="quyche")
    args = parser.parse_args()

    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    client = httpx.Client()

    # ---------------------------------------------------------------- sức khỏe
    print("\n=== 0. Dịch vụ và chỉ mục ===")
    health = client.get(f"{RAG_URL}/health", timeout=30.0).json()
    check("Dịch vụ trả lời", health.get("service") == "rag-service")
    check("Qdrant kết nối được", health["dependencies"]["qdrant"]["ok"])

    collection = f"sa_{args.mode}"
    col = health["collections"].get(collection, {})
    check(
        f"Collection {collection} có dữ liệu",
        col.get("dense_points", 0) > 0,
        f"{col.get('dense_points', 0)} điểm",
    )
    check(
        "Chỉ mục dense và BM25 đồng bộ",
        col.get("in_sync", False),
        f"dense={col.get('dense_points')} bm25={col.get('sparse_documents')}",
    )

    llm_dep = health["dependencies"]["llm"]
    llm_ready = llm_dep["ok"] and not args.no_llm
    if not llm_ready:
        why = "--no-llm" if args.no_llm else (llm_dep.get("detail") or "chưa cấu hình khóa API")
        print(f"\n  Ghi chú: bỏ qua các kiểm tra cần LLM ({why}).")
    else:
        # In ra nhà cung cấp thật sự sẽ phục vụ: cùng một bộ kiểm thử chạy với
        # hai model khác nhau có thể cho hai kết quả khác nhau ở các bước chấm,
        # nên kết quả mà không kèm tên model thì không so sánh được với lần trước.
        print(f"\n  Mô hình ngôn ngữ: {llm_dep.get('provider')} · {llm_dep.get('model')}")

    in_domain = data[f"indomain_{args.mode}"]
    tau = health["config"]["answer_threshold"]

    # ------------------------------------------------- 1. cấu trúc response
    print("\n=== 1. Cấu trúc response (10 câu) ===")
    ten = [q["question"] for q in in_domain] + [q["question"] for q in data["no_answer"]] + [
        q["question"] for q in data["ambiguous"]
    ]
    ten = ten[:10]

    structural_ok = 0
    latencies = []
    for i, q in enumerate(ten, 1):
        try:
            res = query(client, q, args.mode, use_router=llm_ready)
        except Exception as e:  # noqa: BLE001
            check(f"Câu {i} trả về response", False, f"{type(e).__name__}: {e}")
            continue
        missing = REQUIRED_FIELDS - set(res)
        if not missing:
            structural_ok += 1
        latencies.append(res["latency_ms"])
        check(f"Câu {i} đủ trường bắt buộc", not missing, f"thiếu {missing}")

    check("Cả 10 câu đúng cấu trúc", structural_ok == len(ten), f"{structural_ok}/{len(ten)}")
    if latencies:
        latencies.sort()
        print(
            f"        độ trễ: trung vị {latencies[len(latencies) // 2]} ms, "
            f"lớn nhất {latencies[-1]} ms"
        )

    # ------------------------------------------- 2. câu trong phạm vi được trả lời
    print("\n=== 2. Câu trong phạm vi phải được trả lời, kèm trích dẫn ===")
    for item in in_domain:
        res = query(client, item["question"], args.mode, use_router=llm_ready)
        qid = item["id"]

        check(
            f"{qid} vượt ngưỡng tin cậy",
            res["confidence"] >= tau,
            f"conf={res['confidence']:.3f} < τ={tau}",
        )

        if not llm_ready:
            # Không có LLM thì không có câu trả lời sinh ra, nhưng vẫn kiểm được
            # là đoạn văn đúng có được truy xuất hay không.
            if item.get("expected_article"):
                # Xét toàn bộ các điều mà đoạn phủ, không chỉ nhãn chính. Một
                # đoạn trải từ Điều 16 sang Điều 21 vẫn chứa Điều 17; nhìn mỗi
                # nhãn chính sẽ báo trượt cho một lần truy xuất thành công.
                arts: set[str] = set()
                for c in res["retrieved_chunks"]:
                    arts.update(c.get("articles") or [])
                    if c.get("article_number"):
                        arts.add(c["article_number"])
                check(
                    f"{qid} truy xuất được {item['expected_article']}",
                    item["expected_article"] in arts,
                    f"truy xuất được: {sorted(arts)}",
                )
            continue

        check(f"{qid} không bị từ chối", not res["abstained"], res.get("abstain_reason") or "")
        check(f"{qid} có ít nhất một trích dẫn", len(res["citations"]) > 0)

        if item.get("expected_article") and res["citations"]:
            cited = {c.get("article_number") for c in res["citations"]}
            check(
                f"{qid} trích dẫn đúng {item['expected_article']}",
                item["expected_article"] in cited,
                f"trích dẫn: {sorted(a for a in cited if a)}",
            )

        answer_lower = res["answer"].lower()
        hits = [k for k in item.get("expected_keywords", []) if k.lower() in answer_lower]
        check(
            f"{qid} câu trả lời có nội dung mong đợi",
            len(hits) > 0,
            f"không thấy từ khóa nào trong {item.get('expected_keywords')}",
        )

    # ----------------------------------- 3. câu ngoài phạm vi phải bị từ chối
    print("\n=== 3. Câu KHÔNG có căn cứ phải bị từ chối, không được bịa ===")
    for item in data["no_answer"]:
        res = query(client, item["question"], args.mode, use_router=llm_ready)
        qid = item["id"]

        check(
            f"{qid} bị từ chối",
            res["abstained"],
            f"conf={res['confidence']:.3f} τ={tau} — câu trả lời: {res['answer'][:110]!r}",
        )
        check(
            f"{qid} nêu rõ lý do từ chối",
            bool(res.get("abstain_reason")) or "không tìm thấy" in res["answer"].lower(),
        )
        # Kiểm tra quan trọng nhất của cả bộ.
        check(
            f"{qid} KHÔNG bịa ra số điều",
            not (res["abstained"] and ARTICLE_MENTION.search(res["answer"])),
            f"câu trả lời có nhắc điều khoản: {res['answer'][:110]!r}",
        )

    # -------------------------------------- 4. mẫu OOD, kiểm cổng ở quy mô lớn
    print("\n=== 4. Mẫu câu ngoài phạm vi (cổng abstention) ===")
    sample = data["ood"][:8]
    rejected = 0
    for q in sample:
        res = query(client, q, args.mode, use_router=False)
        if res["abstained"]:
            rejected += 1
        else:
            print(f"        không từ chối: {q!r} conf={res['confidence']:.3f}")
    check(
        f"Từ chối ≥ 7/8 câu ngoài phạm vi",
        rejected >= 7,
        f"chỉ từ chối {rejected}/8 — τ={tau} có thể đang quá thấp, chạy lại scripts/calibrate_tau.py",
    )

    # ------------------------------------------------------------------- tổng
    print("\n" + "-" * 62)
    print(f"  PASS: {passed}    FAIL: {failed}")
    if failures:
        print("\n  Các mục không đạt:")
        for f in failures:
            print(f"    · {f}")
    print("-" * 62 + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
