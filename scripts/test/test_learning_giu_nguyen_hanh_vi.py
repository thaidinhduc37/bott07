"""Ba endpoint /learning/* phải giữ nguyên hành vi sau khi bọc chống-bỏ-đi.

Vì sao có tệp này. Ngày 10/08/2026, `/ingest` và `/query` được bọc để dừng tính
khi client bỏ đi. Ba endpoint /learning/* có cùng bệnh nhưng thân hàm nhiều
nhánh trả về sớm, nên phải tách thân ra mới bọc được — và tách thân hàm là lúc
dễ đánh rơi một nhánh nhất. Trước khi refactor thì chưa có bài kiểm thử nào cho
chúng, nên bài này được viết **trước**, để chạy trên mã cũ rồi chạy lại trên mã
mới và so xem có gì đổi không.

Nó ghim đúng những nhánh mà việc tách thân hàm có thể làm hỏng:

  * nhánh từ chối vì độ tin cậy dưới ngưỡng (trả 200, `abstained`)
  * nhánh mô hình ngôn ngữ không dùng được (trả 503)

Không cần hạn mức LLM: nhánh thứ nhất không gọi mô hình, nhánh thứ hai chỉ đúng
khi mô hình *không* gọi được — mà đó lại là tình trạng thật lúc viết bài này.

    python scripts/test/test_learning_giu_nguyen_hanh_vi.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
TOKEN = ""

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


def goi(path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Internal-Token": TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"detail": body}


# Câu chắc chắn không có trong giáo trình — dùng để ép nhánh từ chối.
NGOAI_PHAM_VI = "cách nướng bánh mì bằng nồi chiên không dầu"
# Câu bám vào giáo trình — dùng để đi tới bước gọi mô hình.
TRONG_PHAM_VI = "kiến thức trong giáo trình"


def main() -> int:
    global TOKEN
    env = (Path(__file__).resolve().parents[2] / ".env").read_text(encoding="utf-8")
    for line in env.splitlines():
        if line.startswith("RAG_INTERNAL_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip()

    # --- /summarise ------------------------------------------------------
    ma, body = goi("/learning/summarise", {"topic": NGOAI_PHAM_VI, "top_k": 8})
    check("summarise: câu ngoài phạm vi trả 200", ma == 200, f"nhận {ma}: {body}")
    check(
        "summarise: câu ngoài phạm vi bị từ chối",
        body.get("abstained") is True,
        str(body)[:200],
    )
    check(
        "summarise: từ chối thì không kèm trích dẫn nào",
        body.get("citations") == [],
        str(body.get("citations"))[:200],
    )
    check(
        "summarise: vẫn báo độ tin cậy và ngưỡng",
        isinstance(body.get("confidence"), (int, float))
        and isinstance(body.get("threshold"), (int, float))
        and body["confidence"] < body["threshold"],
        f"conf={body.get('confidence')} tau={body.get('threshold')}",
    )

    # Nhánh trên ngưỡng đi qua mô hình ngôn ngữ. Chấp nhận cả 503 để bài kiểm
    # thử không phụ thuộc hạn mức API — điều cần ghim là *hình dạng* của phản
    # hồi ở mỗi nhánh, vì đó mới là thứ việc tách thân hàm có thể làm hỏng.
    ma, body = goi("/learning/summarise", {"topic": TRONG_PHAM_VI, "top_k": 8})
    check(
        "summarise: trên ngưỡng thì trả tóm tắt có nguồn, hoặc 503 nếu LLM hỏng",
        (ma == 200 and body.get("abstained") is False and bool(body.get("summary")))
        or (ma == 200 and body.get("abstained") is True)
        or ma == 503,
        f"nhận {ma}: {str(body)[:200]}",
    )
    if ma == 200 and body.get("abstained") is False:
        check(
            "summarise: tóm tắt thật thì phải kèm đoạn văn truy xuất được",
            bool(body.get("retrieved_chunks")),
            str(body)[:200],
        )

    # --- /quiz -----------------------------------------------------------
    ma, body = goi("/learning/quiz", {"topic": NGOAI_PHAM_VI, "n_questions": 3, "top_k": 8})
    check("quiz: câu ngoài phạm vi trả 200", ma == 200, f"nhận {ma}: {body}")
    check("quiz: câu ngoài phạm vi bị từ chối", body.get("abstained") is True, str(body)[:200])
    check("quiz: từ chối thì không sinh câu hỏi nào", body.get("questions") == [], str(body)[:200])
    check(
        "quiz: nêu rõ lý do từ chối",
        bool(body.get("abstain_reason")),
        str(body.get("abstain_reason"))[:200],
    )

    ma, body = goi("/learning/quiz", {"topic": TRONG_PHAM_VI, "n_questions": 3, "top_k": 8})
    check(
        "quiz: trên ngưỡng thì sinh câu hỏi, hoặc 503 nếu LLM hỏng",
        (ma == 200 and body.get("abstained") is False and bool(body.get("questions")))
        or (ma == 200 and body.get("abstained") is True)
        or ma == 503,
        f"nhận {ma}: {str(body)[:200]}",
    )
    if ma == 200 and body.get("questions"):
        q = body["questions"][0]
        check(
            "quiz: mỗi câu có đúng 4 lựa chọn và chỉ số đáp án nằm trong phạm vi",
            len(q.get("options", [])) == 4 and 0 <= q.get("correct_index", -1) < 4,
            str(q)[:200],
        )

    # --- /grade ----------------------------------------------------------
    ma, body = goi(
        "/learning/grade",
        {
            "items": [{"question": "1+1?", "correct": 0, "chosen": 1, "explanation": "…"}],
            "score": 0.0,
        },
    )
    check(
        "grade: trả nhận xét, hoặc 503 nếu LLM hỏng",
        (ma == 200 and bool(body.get("feedback"))) or ma == 503,
        f"nhận {ma}: {str(body)[:200]}",
    )

    print(f"\n{PASSED}/{PASSED + FAILED} kiểm tra đạt")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
