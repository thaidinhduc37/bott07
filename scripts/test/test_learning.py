"""Kiểm thử /learning: sinh đề từ giáo trình, chấm bài, sổ câu sai (Leitner).

Cần API chạy ở localhost:5000 và đã `alembic upgrade head`. Bước sinh đề cần
LLM; nếu LLM hết hạn mức (503) thì các bước phụ thuộc được bỏ qua, không tính
là lỗi. Bước "đến hạn ôn" kéo `due_at` về quá khứ bằng psql trong container
`sa-postgres-dev`.

    python scripts/test/test_learning.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import Client, check, login, psql  # noqa: E402

sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
sv2 = login("sv.tranthimai@hvktcnan.edu.vn")

print("\n[1] Chưa đăng nhập / id sai")
check("GET /learning/quiz không cookie -> 401", Client().req("GET", "/learning/quiz")[0] == 401)
check("id không phải UUID -> 404", sv.req("GET", "/learning/quiz/abc")[0] == 404)
s, b = sv.req("POST", "/learning/quiz", {"topic": "ab"})
check("chủ đề quá ngắn -> 400", s == 400, str(b))
s, b = sv.req("POST", "/learning/quiz", {"topic": "mã hóa", "nQuestions": 50})
check("nQuestions > 10 -> 400", s == 400, str(b))

print("\n[2] Chủ đề ngoài giáo trình -> từ chối, không tạo lượt")
before = sv.req("GET", "/learning/quiz")[1]["total"]
s, b = sv.req("POST", "/learning/quiz", {"topic": "công thức nấu phở bò Nam Định ngon nhất"})
if s == 503:
    print("  SKIP  LLM không dùng được")
else:
    check("abstained = true", s == 200 and b.get("abstained") is True, f"{s} {b}")
    check("không tạo lượt làm bài", sv.req("GET", "/learning/quiz")[1]["total"] == before)

print("\n[3] Sinh đề theo môn")
courses = sv.req("GET", "/chat/courses")[1]["items"]
cs304 = next((c for c in courses if c["code"] == "CS304"), None)
s, b = sv.req(
    "POST", "/learning/quiz",
    {"topic": "tấn công từ chối dịch vụ DoS và cách phòng chống", "courseId": cs304 and cs304["id"], "nQuestions": 3},
)
session = None
if s == 503:
    print(f"  SKIP  LLM không dùng được: {b}")
elif s == 200 and b.get("abstained"):
    print(f"  SKIP  bị từ chối: {b.get('reason')}")
else:
    check("200 + có session", s == 200 and b.get("session"), f"{s} {b}")
    session = b.get("session")

if session:
    qs = session["questions"]
    check("có câu hỏi, mỗi câu 4 phương án", len(qs) >= 1 and all(len(q["options"]) == 4 for q in qs))
    check("chưa nộp thì KHÔNG lộ đáp án", all("correctIndex" not in q and "explanation" not in q for q in qs))
    check("chưa nộp: status IN_PROGRESS", session["status"] == "IN_PROGRESS")

    print("\n[4] Học viên khác không xem/nộp được")
    check("sv2 GET -> 404", sv2.req("GET", f"/learning/quiz/{session['id']}")[0] == 404)
    check("sv2 submit -> 404", sv2.req("POST", f"/learning/quiz/{session['id']}/submit", {"answers": []})[0] == 404)

    print("\n[5] Nộp bài: câu 1 bỏ trống, còn lại chọn A")
    answers = [{"questionId": q["id"], "selectedIndex": 0} for q in qs[1:]]
    s, graded = sv.req("POST", f"/learning/quiz/{session['id']}/submit", {"answers": answers})
    check("200", s == 200, f"{s} {graded}")
    gq = graded["questions"]
    check("đã lộ đáp án + giải thích", all("correctIndex" in q and "explanation" in q for q in gq))
    check("câu bỏ trống tính sai", gq[0]["isCorrect"] is False and gq[0]["selectedIndex"] is None)
    n_right = sum(q["isCorrect"] for q in gq)
    check("điểm = đúng/tổng*10", graded["score"] == round(n_right / len(gq) * 10, 1), str(graded["score"]))
    check("nộp lần hai -> 409", sv.req("POST", f"/learning/quiz/{session['id']}/submit", {"answers": []})[0] == 409)
    print(f"        nhận xét: {(graded.get('feedback') or '(không có — LLM lỗi?)')[:120]}")

    print("\n[6] Sổ câu sai")
    ov = sv.req("GET", "/learning/review-items")[1]
    wrong_q = {q["question"] for q in gq if not q["isCorrect"]}
    in_book = {i["question"] for i in ov["items"]}
    check("mọi câu sai đều vào sổ", wrong_q <= in_book)
    check("sv2 không thấy sổ của sv", not (wrong_q & {i["question"] for i in sv2.req("GET", "/learning/review-items")[1]["items"]}))
    item = next(i for i in ov["items"] if i["question"] in wrong_q)
    check("câu sai mới: hộp 1, chưa đến hạn (mai mới ôn)", item["box"] == 1 and not item["isDue"], str(item))

    print("\n[7] Đến hạn -> lượt ôn câu sai, làm đúng thì lên hộp")
    psql(f"update review_items set due_at = now() - interval '1 minute' where id = '{item['id']}'")
    s, rv = sv.req("POST", "/learning/review", {"limit": 20})
    check("tạo lượt ôn 200", s == 200, f"{s} {rv}")
    rq = next((q for q in rv.get("questions", []) if q["question"] == item["question"]), None)
    check("câu đến hạn có trong lượt ôn, đánh dấu fromReview", rq is not None and rq["fromReview"])
    if rq:
        s, rg = sv.req(
            "POST", f"/learning/quiz/{rv['id']}/submit",
            {"answers": [{"questionId": rq["id"], "selectedIndex": item["correctIndex"]}]},
        )
        after = next(i for i in sv.req("GET", "/learning/review-items")[1]["items"] if i["id"] == item["id"])
        check("làm đúng -> hộp 2, hẹn 3 ngày", after["box"] == 2 and not after["isDue"], str(after))

    print("\n[8] Xóa khỏi sổ")
    check("sv2 xóa câu của sv -> 404", sv2.req("DELETE", f"/learning/review-items/{item['id']}")[0] == 404)
    check("sv xóa -> 200", sv.req("DELETE", f"/learning/review-items/{item['id']}")[0] == 200)

print("\n[9] Không có câu đến hạn -> 409 NOTHING_DUE")
psql(
    "update review_items set due_at = now() + interval '1 day' where user_id = "
    "(select id from users where email = 'sv.tranthimai@hvktcnan.edu.vn') and due_at is not null"
)
s, b = sv2.req("POST", "/learning/review", {})
check("409", s == 409 and b.get("code") == "NOTHING_DUE", f"{s} {b}")

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
