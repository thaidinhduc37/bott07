"""Kiểm thử /learning/notes (sổ tay) và /learning/exam-plan (kế hoạch ôn thi).

Không cần LLM. Cần API ở localhost:5000, `alembic upgrade head`, và dữ liệu seed
(lịch thi của lớp học viên demo). Bước lưu câu trắc nghiệm vào sổ tay tạo một
lượt ôn giả bằng psql trong container `sa-postgres-dev`.

    python scripts/test/test_notes_exam_plan.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as T  # noqa: E402
from _http import Client, check, login, psql  # noqa: E402

sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
sv2 = login("sv.tranthimai@hvktcnan.edu.vn")
uid = psql("select id from users where email = 'sv.nguyenducanh@hvktcnan.edu.vn'")

print("\n[1] Kế hoạch ôn thi")
s, plan = sv.req("GET", "/learning/exam-plan")
check("200", s == 200, str(plan)[:200])
exams = plan.get("exams", [])
check("có kỳ thi sắp tới của lớp", len(exams) > 0)
if exams:
    e = exams[0]
    check("sắp theo ngày thi tăng dần", [x["examDate"] for x in exams] == sorted(x["examDate"] for x in exams))
    check("daysLeft không âm", all(x["daysLeft"] >= 0 for x in exams))
    check("kế hoạch tối đa 14 ngày, ngày cuối là tổng ôn",
          all(len(x["plan"]) <= 14 and (not x["plan"] or x["plan"][-1]["kind"] == "FINAL") for x in exams))
    check("mọi khoảng trong kế hoạch kết thúc trước ngày thi, from <= to",
          all(all(d["from"] <= d["to"] < x["examDate"] for d in x["plan"]) for x in exams))
    check("các khoảng liền nhau, không chồng lấn",
          all(all(a["to"] < b["from"] for a, b in zip(x["plan"], x["plan"][1:])) for x in exams))
    with_docs = [x for x in exams if x["materials"]]
    check("môn có giáo trình thì kế hoạch nhắc tới giáo trình",
          all(any(d["kind"] == "DOC" for d in x["plan"]) for x in with_docs if len(x["plan"]) > 1))
    check("readiness là một trong 3 nhãn", all(x["progress"]["readiness"] in ("CHUA_ON", "CAN_ON_THEM", "ON_DINH") for x in exams))
check("chưa đăng nhập -> 401", Client().req("GET", "/learning/exam-plan")[0] == 401)

print("\n[2] Ghi chú tự viết")
s, n = sv.req("POST", "/learning/notes", {"title": "Ghi nhớ SYN cookies", "content": "Không cấp phát trước khi nhận ACK."})
check("tạo 200", s == 200 and n.get("sourceType") == "MANUAL", str(n))
nid = n.get("id")
check("sv2 không thấy ghi chú của sv",
      all(x["id"] != nid for x in sv2.req("GET", "/learning/notes")[1]["items"]))
check("sv2 sửa -> 404", sv2.req("PATCH", f"/learning/notes/{nid}", {"note": "x"})[0] == 404)
s, n2 = sv.req("PATCH", f"/learning/notes/{nid}", {"note": "ôn trước thi", "pinned": True})
check("sửa ghi chú riêng + ghim", s == 200 and n2["pinned"] and n2["note"] == "ôn trước thi", str(n2))
s, found = sv.req("GET", "/learning/notes?q=cookies")
check("tìm kiếm theo từ khóa", any(x["id"] == nid for x in found["items"]))
check("ghim đứng đầu", sv.req("GET", "/learning/notes")[1]["items"][0]["id"] == nid)
check("courseId không tồn tại -> 404",
      sv.req("POST", "/learning/notes", {"title": "a", "content": "b", "courseId": str(uuid.uuid4())})[0] == 404)
check("trường lạ -> 400", sv.req("POST", "/learning/notes", {"title": "a", "content": "b", "userId": uid})[0] == 400)

print("\n[3] Lưu câu trắc nghiệm")
sid, qid = str(uuid.uuid4()), str(uuid.uuid4())
psql(
    f"insert into quiz_sessions (id, user_id, topic, status) values ('{sid}', '{uid}', '[test] ghi chú', 'IN_PROGRESS');"
    f"insert into quiz_questions (id, session_id, ordinal, question, options, correct_index, explanation, source_file, source_page)"
    f" values ('{qid}', '{sid}', 1, '[test] Câu hỏi?', '[\"A\",\"B\",\"C\",\"D\"]', 2, 'vì C', 'x.pdf', 3)"
)
s, b = sv.req("POST", "/learning/notes/from-quiz", {"sourceId": qid})
check("chưa nộp bài -> 409 (không lộ đáp án)", s == 409, f"{s} {b}")
psql(f"update quiz_sessions set status = 'SUBMITTED' where id = '{sid}'")
check("sv2 lưu câu của sv -> 404", sv2.req("POST", "/learning/notes/from-quiz", {"sourceId": qid})[0] == 404)
s, qn = sv.req("POST", "/learning/notes/from-quiz", {"sourceId": qid})
check("đã nộp -> lưu được, kèm đáp án + nguồn",
      s == 200 and "C. C" in qn["content"] and qn["citations"][0]["page"] == 3, str(qn))
s, again = sv.req("POST", "/learning/notes/from-quiz", {"sourceId": qid})
check("lưu lần hai trả lại ghi chú cũ, không nhân bản", again.get("id") == qn.get("id"))
check("không sửa được nội dung chép từ nguồn",
      sv.req("PATCH", f"/learning/notes/{qn['id']}", {"content": "sửa bừa"})[0] == 409)
psql(f"delete from quiz_sessions where id = '{sid}'")
check("xóa lượt ôn gốc, ghi chú vẫn còn",
      any(x["id"] == qn["id"] for x in sv.req("GET", "/learning/notes")[1]["items"]))

print("\n[4] Lưu câu trả lời hỏi đáp")
row = psql(
    "select m.id, m.abstained from chat_messages m join chat_conversations c on c.id = m.conversation_id "
    f"where c.user_id = '{uid}' and m.role = 'ASSISTANT' order by m.abstained nulls first limit 1"
)
if not row:
    print("  SKIP  học viên demo chưa có câu trả lời hỏi đáp nào")
else:
    mid, abstained = row.split("|")
    s, cn = sv.req("POST", "/learning/notes/from-chat", {"sourceId": mid})
    if abstained == "t":
        check("câu từ chối -> 409", s == 409, f"{s} {cn}")
    else:
        check("lưu câu trả lời 200, tiêu đề là câu hỏi", s == 200 and cn["sourceType"] == "CHAT", f"{s} {cn}")
        sv.req("DELETE", f"/learning/notes/{cn['id']}")
    check("sv2 lưu câu trả lời của sv -> 404", sv2.req("POST", "/learning/notes/from-chat", {"sourceId": mid})[0] == 404)

print("\n[5] Dọn")
check("sv xóa ghi chú", sv.req("DELETE", f"/learning/notes/{nid}")[0] == 200)
sv.req("DELETE", f"/learning/notes/{qn['id']}")

print(f"\n{T.PASSED} đạt, {T.FAILED} lỗi")
sys.exit(1 if T.FAILED else 0)
