"""Kiểm thử /learning/insights/* — thống kê ẩn danh cho giảng viên / QLĐT.

Tạo câu sai giả cho 2 học viên ở môn CS301 (giảng viên phụ trách:
gv.nguyenvanminh) bằng psql trong container `sa-postgres-dev`, rồi dọn lại.

    python scripts/test/test_insights.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")      # phụ trách CS301
gv2 = login("gv.lehoanganh@hvktcnan.edu.vn")        # không phụ trách môn nào
qldt = login("qldt@hvktcnan.edu.vn")

cs301 = psql("select id from courses where code = 'CS301'")
cs302 = psql("select id from courses where code = 'CS302'")
u1 = psql("select id from users where email = 'sv.nguyenducanh@hvktcnan.edu.vn'")
u2 = psql("select id from users where email = 'sv.tranthimai@hvktcnan.edu.vn'")
opts = json.dumps(["A1", "B1", "C1", "D1"])


def seed(user: str, qhash: str, question: str, wrong: int) -> None:
    psql(
        "insert into review_items (id, user_id, course_id, question_hash, question, options, correct_index, "
        f"explanation, box, due_at, times_wrong) values (gen_random_uuid(), '{user}', '{cs301}', '{qhash}', "
        f"'{question}', '{opts}', 1, 'x', 1, now() + interval '1 day', {wrong})"
    )


psql("delete from review_items where question like '[insight]%'")
seed(u1, "insight-common", "[insight] Câu nhiều người sai", 2)
seed(u2, "insight-common", "[insight] Câu nhiều người sai", 1)
seed(u1, "insight-single", "[insight] Câu chỉ một người sai", 5)

try:
    print("\n[1] Phân quyền")
    check("học viên -> 403", sv.req("GET", "/learning/insights/courses")[0] == 403)
    s, ov = gv.req("GET", "/learning/insights/courses")
    check("giảng viên chỉ thấy môn mình phụ trách", s == 200 and [i["course"]["code"] for i in ov["items"]] == ["CS301"], str(ov))
    check("giảng viên không phụ trách môn nào -> danh sách rỗng", gv2.req("GET", "/learning/insights/courses")[1]["items"] == [])
    check("giảng viên xem môn người khác -> 404", gv.req("GET", f"/learning/insights/courses/{cs302}")[0] == 404)
    check("QLĐT thấy mọi môn", len(qldt.req("GET", "/learning/insights/courses")[1]["items"]) >= 8)
    check("giảng viên xem câu bị từ chối -> 403", gv.req("GET", "/learning/insights/unanswered")[0] == 403)

    print("\n[2] Câu nhiều học viên sai (ẩn danh, ngưỡng 2 người)")
    s, d = gv.req("GET", f"/learning/insights/courses/{cs301}")
    check("200", s == 200, str(d)[:200])
    qs = {q["question"]: q for q in d.get("hardQuestions", [])}
    common = qs.get("[insight] Câu nhiều người sai")
    check("câu 2 người sai có mặt, đếm đúng", common is not None and common["learners"] == 2 and common["timesWrong"] == 3, str(common))
    check("kèm đáp án đúng", common is not None and common["correctAnswer"] == "B. B1", str(common))
    check("câu chỉ 1 người sai bị ẩn (dưới ngưỡng)", "[insight] Câu chỉ một người sai" not in qs)
    body = json.dumps(d, ensure_ascii=False)
    check("không lộ id/email học viên", u1 not in body and u2 not in body and "@" not in body)

    print("\n[3] Câu hỏi hệ thống từ chối trả lời")
    s, un = qldt.req("GET", "/learning/insights/unanswered")
    check("QLĐT 200", s == 200, str(un)[:200])
    check("mỗi mục có nội dung câu hỏi, không có thông tin người hỏi",
          all(set(i) == {"question", "mode", "confidence", "createdAt"} and i["question"] for i in un.get("items", [])))
finally:
    psql("delete from review_items where question like '[insight]%'")

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
