"""Kiểm thử GET /learning/progress — tiến trình ôn tập của chính học viên.

Chèn vài lượt đã nộp + câu sai giả cho một học viên qua psql, kiểm tra số liệu
gộp, rồi dọn lại.

    python scripts/test/test_progress.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

EMAIL = "sv.tranthimai@hvktcnan.edu.vn"
sv = login(EMAIL)
uid = psql(f"select id from users where email = '{EMAIL}'")
cs = psql("select id from courses where code = 'CS301'")
opts = json.dumps(["A1", "B1", "C1", "D1"])
TAG = "__progress_test__"


def cleanup() -> None:
    psql(f"delete from quiz_sessions where user_id = '{uid}' and topic like '{TAG}%'")
    psql(f"delete from review_items where user_id = '{uid}' and question like '{TAG}%'")


cleanup()
base_status, base = sv.req("GET", "/learning/progress")
check("có phản hồi 200", base_status == 200, str(base_status))
b_week, b_total = base["week"]["sessions"], base["totalSessions"]

try:
    for i, (ago, score) in enumerate([(0, 8.0), (1, 6.0), (2, 4.0)]):
        psql(
            f"insert into quiz_sessions (id, user_id, course_id, topic, status, score, submitted_at, created_at) "
            f"values (gen_random_uuid(), '{uid}', '{cs}', '{TAG}{i}', 'SUBMITTED', {score}, "
            f"now() - interval '{ago} day', now() - interval '{ago} day')"
        )
    psql(
        f"insert into review_items (id, user_id, course_id, question_hash, question, options, correct_index, "
        f"explanation, box, due_at, times_wrong, times_right, created_at, updated_at) values "
        f"(gen_random_uuid(), '{uid}', '{cs}', '{TAG}h1', '{TAG} q1', '{opts}', 0, 'e', 1, now() - interval '1 hour', 1, 0, now(), now()), "
        f"(gen_random_uuid(), '{uid}', '{cs}', '{TAG}h2', '{TAG} q2', '{opts}', 0, 'e', 4, NULL, 1, 3, now(), now())"
    )
    st, p = sv.req("GET", "/learning/progress")
    check("tổng số lượt tăng 3", p["totalSessions"] == b_total + 3, str(p["totalSessions"]))
    check("tuần này tăng 3", p["week"]["sessions"] == b_week + 3, str(p["week"]))
    check("hoạt động đủ 14 ngày", len(p["activity"]) == 14)
    check("hôm nay có ít nhất 1 lượt", p["activity"][-1]["count"] >= 1)
    check("chuỗi ngày >= 3", p["streakDays"] >= 3, str(p["streakDays"]))
    c = next((x for x in p["courses"] if x["course"]["code"] == "CS301"), None)
    check("có môn CS301", c is not None)
    if c:
        check("câu đến hạn tính đúng", c["reviewDue"] >= 1, str(c))
        check("câu đã thuộc tính đúng", c["mastered"] >= 1, str(c))
        check("điểm lượt gần nhất là 8", c["lastScore"] == 8.0, str(c["lastScore"]))
    check("không lộ id người khác", "userId" not in json.dumps(p))
finally:
    cleanup()

anon = H.Client()
st, _ = anon.req("GET", "/learning/progress")
check("chưa đăng nhập bị từ chối", st in (401, 403), str(st))

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
