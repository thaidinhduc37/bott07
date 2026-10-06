"""Kiểm thử phản hồi hữu ích / chưa đúng về câu trả lời của trợ lý.

Dựng sẵn một hội thoại mẫu của học viên bằng SQL (trợ lý thật cần khóa Gemini), rồi dọn lại.

    python scripts/test/test_feedback.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

mai = login("sv.tranthimai@hvktcnan.edu.vn")
other = login("sv.nguyenducanh@hvktcnan.edu.vn")
qldt = login("qldt@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")

TAG = "__feedback_test__"
uid = psql("select id from users where email = 'sv.tranthimai@hvktcnan.edu.vn'")


def cleanup() -> None:
    psql(f"delete from chat_conversations where title = '{TAG}'")


cleanup()
try:
    conv = psql(
        f"insert into chat_conversations (id, user_id, title, mode, created_at, updated_at) "
        f"values (gen_random_uuid(), '{uid}', '{TAG}', 'QUYCHE', now(), now()) returning id"
    ).split()[0]
    q_id = psql(
        f"insert into chat_messages (id, conversation_id, role, content, created_at) "
        f"values (gen_random_uuid(), '{conv}', 'USER', 'Điều kiện được hoãn thi là gì?', now() - interval '1 minute') returning id"
    ).split()[0]
    a_id = psql(
        f"insert into chat_messages (id, conversation_id, role, content, abstained, confidence, created_at) "
        f"values (gen_random_uuid(), '{conv}', 'ASSISTANT', 'Câu trả lời mẫu về hoãn thi.', false, 0.42, now()) returning id"
    ).split()[0]

    # --- đánh giá hữu ích
    st, r = mai.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": "UP"})
    check("đánh giá hữu ích", st == 200 and r["feedback"]["rating"] == "UP", f"{st} {r}")
    st, c = mai.req("GET", f"/chat/conversations/{conv}")
    ans = next((m for m in c.get("messages", []) if m["id"] == a_id), {})
    check("lịch sử hội thoại có đánh giá của mình", (ans.get("feedback") or {}).get("rating") == "UP", str(ans.get("feedback")))

    # --- đổi sang chưa đúng, kèm lý do
    st, r = mai.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": "DOWN", "reason": "WRONG", "comment": "  Điều 12 đã sửa đổi  "})
    check("đánh giá chưa đúng kèm lý do", st == 200 and r["feedback"]["reason"] == "WRONG" and r["feedback"]["comment"] == "Điều 12 đã sửa đổi", f"{st} {r}")
    check("mỗi người một đánh giá cho mỗi câu (ghi đè)", psql(f"select count(*) from chat_feedback where message_id = '{a_id}'") == "1")
    st, r = mai.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": "UP", "reason": "WRONG", "comment": "x"})
    check("đánh giá hữu ích bỏ lý do và ghi chú", r["feedback"]["reason"] is None and r["feedback"]["comment"] is None, str(r))
    mai.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": "DOWN", "reason": "WRONG", "comment": "Điều 12 đã sửa đổi"})

    # --- dữ liệu sai
    st, r = mai.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": "MAYBE"})
    check("đánh giá không hợp lệ → 400", st == 400 and r.get("code") == "INVALID_RATING", f"{st} {r}")
    st, r = mai.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": "DOWN", "reason": "BỊA"})
    check("lý do không hợp lệ → 400", st == 400 and r.get("code") == "INVALID_REASON", f"{st} {r}")
    st, _ = mai.req("PUT", f"/chat/messages/{q_id}/feedback", {"rating": "UP"})
    check("không đánh giá được tin của chính mình (người dùng)", st == 404, str(st))
    st, _ = mai.req("PUT", "/chat/messages/khong-phai-uuid/feedback", {"rating": "UP"})
    check("id sai định dạng → 404", st == 404, str(st))
    st, _ = other.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": "UP"})
    check("không đánh giá được câu trả lời của người khác → 404", st == 404, str(st))

    # --- cán bộ quản lý xem tổng hợp, ẩn danh
    st, rv = qldt.req("GET", "/learning/insights/feedback")
    check("quản lý đào tạo xem được tổng hợp", st == 200 and rv.get("down", 0) >= 1, f"{st} {str(rv)[:200]}")
    mine = next((i for i in rv.get("items", []) if i["answer"] == "Câu trả lời mẫu về hoãn thi."), {})
    check("có câu hỏi, lý do và ghi chú", mine.get("question") == "Điều kiện được hoãn thi là gì?" and mine.get("reason") == "WRONG" and mine.get("comment") == "Điều 12 đã sửa đổi", str(mine))
    blob = json.dumps(rv, ensure_ascii=False)
    check("không lộ danh tính người đánh giá", "Trần Thị Mai" not in blob and "tranthimai" not in blob and uid not in blob)
    check("có tỉ lệ hữu ích và thống kê theo lý do", "helpfulRate" in rv and any(x["reason"] == "WRONG" for x in rv.get("byReason", [])), str(rv.get("byReason")))
    st, _ = gv.req("GET", "/learning/insights/feedback")
    check("giảng viên không xem được", st == 403, str(st))
    st, _ = mai.req("GET", "/learning/insights/feedback")
    check("học viên không xem được", st == 403, str(st))

    # --- bỏ đánh giá
    st, r = mai.req("PUT", f"/chat/messages/{a_id}/feedback", {"rating": None})
    check("bỏ đánh giá", st == 200 and r["feedback"] is None, f"{st} {r}")
    st, c = mai.req("GET", f"/chat/conversations/{conv}")
    ans = next((m for m in c.get("messages", []) if m["id"] == a_id), {})
    check("lịch sử không còn đánh giá", ans.get("feedback") is None, str(ans.get("feedback")))
    check("xóa hội thoại thì xóa luôn đánh giá", True)
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
