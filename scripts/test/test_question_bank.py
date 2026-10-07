"""Kiểm thử ngân hàng câu hỏi: nhập CSV (giảng viên), học viên ôn từ ngân hàng, và xuất CSV danh sách lớp.

Câu hỏi thử bắt đầu bằng "ZT" và được dọn lại ở cuối (kể cả khi có lỗi).

    python scripts/test/test_question_bank.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import BASE, check, login, psql  # noqa: E402

gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")   # phụ trách CS301
gv2 = login("gv.lehoanganh@hvktcnan.edu.vn")     # không phụ trách môn nào
sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
qldt = login("qldt@hvktcnan.edu.vn")

cs301 = psql("select id from courses where code = 'CS301'")
b3d15 = psql("select id from classes where code = 'B3D15'")
HEAD = "cau_hoi,a,b,c,d,dap_an,giai_thich,chuong\n"


def cleanup() -> None:
    psql("delete from quiz_sessions where topic like 'ZT%'")
    psql("delete from review_items where question like 'ZT%'")
    psql("delete from bank_questions where question like 'ZT%'")


def upload(client, course_id: str, content: str, dry: bool = False) -> tuple[int, dict]:
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="cau-hoi.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n{content}\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        BASE + f"/question-bank/import?courseId={course_id}" + ("&dryRun=true" if dry else ""), data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with client.opener.open(req, timeout=60) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def raw_get(client, path: str) -> tuple[int, bytes, dict]:
    try:
        with client.opener.open(BASE + path, timeout=60) as res:
            return res.status, res.read(), dict(res.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {}


good = HEAD + (
    "ZT Thủ đô của Việt Nam?,Hà Nội,Huế,Đà Nẵng,Cần Thơ,A,Hà Nội là thủ đô,Chương 1\n"
    "ZT 2 + 2 bằng?,3,4,5,,B,,\n"
    "ZT Mã hóa đối xứng dùng?,Một khóa chung,Hai khóa,,,A,Cùng một khóa để mã và giải mã,Chương 2\n"
)

cleanup()
try:
    # --- quyền và phạm vi
    st, d = gv.req("GET", "/question-bank/courses")
    check("giảng viên thấy môn mình phụ trách", st == 200 and [c["code"] for c in d["items"]] == ["CS301"], f"{st} {str(d)[:200]}")
    st, d = gv2.req("GET", "/question-bank/courses")
    check("giảng viên không có môn → rỗng", st == 200 and d["items"] == [], str(d)[:200])
    st, _ = upload(gv2, cs301, good, dry=True)
    check("môn của người khác → 404", st == 404, str(st))
    st, _ = upload(sv, cs301, good, dry=True)
    check("học viên không nhập được", st == 403, str(st))
    st, d = qldt.req("GET", "/question-bank/courses")
    check("quản lý thấy mọi môn", st == 200 and len(d["items"]) >= 2, f"{st} {len(d.get('items', []))}")

    # --- chạy thử và dòng lỗi
    st, d = upload(gv, cs301, good, dry=True)
    check("chạy thử hợp lệ", st == 200 and d["dryRun"] and d["created"] == 3 and not d["errors"], f"{st} {str(d)[:300]}")
    check("chạy thử không ghi", psql("select count(*) from bank_questions where question like 'ZT%'") == "0")
    bad = HEAD + (
        ",A,B,,,A,,\n"                                  # thiếu câu hỏi
        "ZT một đáp án,A,,,,A,,\n"                      # chỉ 1 đáp án
        "ZT bỏ trống giữa,A,B,,D,A,,\n"                  # đáp án không liền nhau
        "ZT sai đáp án,A,B,,,C,,\n"                      # đáp án đúng trỏ vào ô trống
        "ZT trùng đáp án,A,a,,,A,,\n"                    # hai đáp án giống nhau
        "ZT không chữ cái,A,B,,,2,,\n"                   # dap_an không phải chữ cái
    )
    st, d = upload(gv, cs301, bad)
    check("báo đủ 6 dòng lỗi, không ghi", st == 200 and {e["line"] for e in d["errors"]} == {2, 3, 4, 5, 6, 7} and not d["accepted"], f"{st} {str(d)[:300]}")
    st, d = upload(gv, cs301, "a,b\n1,2\n")
    check("thiếu cột bắt buộc → 400", st == 400 and d.get("code") == "BAD_HEADER", f"{st} {d}")

    # --- nhập thật và nhập lại
    st, d = upload(gv, cs301, good)
    check("nhập thật 3 câu", st == 200 and d["accepted"] and d["created"] == 3, f"{st} {str(d)[:300]}")
    st, d = upload(gv, cs301, good)
    check("nhập lại không trùng", st == 200 and d["created"] == 0 and d["unchanged"] == 3, f"{st} {str(d)[:300]}")
    st, d = gv.req("GET", f"/question-bank/questions?courseId={cs301}")
    check("danh sách có đáp án cho giảng viên", st == 200 and d["total"] == 3 and all("correctIndex" in q for q in d["items"]), f"{st} {str(d)[:200]}")
    q2 = next(q for q in d["items"] if q["question"].startswith("ZT 2 + 2"))
    check("giải thích mặc định khi để trống", q2["explanation"].startswith("Đáp án đúng"), q2["explanation"])
    check("đáp án đúng B → chỉ số 1", q2["correctIndex"] == 1 and len(q2["options"]) == 3)

    # --- học viên ôn từ ngân hàng
    st, d = sv.req("GET", "/learning/bank")
    check("học viên biết môn có ngân hàng", st == 200 and any(i["courseId"] == cs301 and i["count"] >= 3 for i in d["items"]), str(d)[:200])
    st, r = sv.req("POST", "/learning/quiz", {"source": "bank", "courseId": cs301, "nQuestions": 3, "topic": "ZT ôn thử", "includeReview": False})
    sess = r.get("session", {})
    qs = sess.get("questions", [])
    check("tạo đề từ ngân hàng", st == 200 and not r.get("abstained") and len(qs) == 3, f"{st} {str(r)[:300]}")
    check("chưa nộp thì không lộ đáp án", all("correctIndex" not in q and "explanation" not in q for q in qs))
    st, r2 = sv.req("POST", "/learning/quiz", {"source": "bank", "nQuestions": 3})
    check("ôn từ ngân hàng phải chọn môn", st == 400, str(st))
    st, r2 = sv.req("POST", "/learning/quiz", {"source": "ai", "nQuestions": 3, "topic": "ab"})
    check("chế độ AI vẫn đòi chủ đề ≥ 3 ký tự", st == 400, str(st))

    # Trả lời sai câu "2 + 2" (chọn A), còn lại chọn đúng bằng cách tra đáp án trong DB.
    answers = []
    for q in qs:
        correct = int(psql(f"select correct_index from quiz_questions where id='{q['id']}'"))
        pick = 0 if q["question"].startswith("ZT 2 + 2") else correct
        answers.append({"questionId": q["id"], "selectedIndex": pick})
    st, done = sv.req("POST", f"/learning/quiz/{sess['id']}/submit", {"answers": answers})
    check("nộp bài chấm đúng 2/3 (thang 10)", st == 200 and done.get("status") == "SUBMITTED" and done.get("score") == 6.7, f"{st} {done.get('score')}")
    check("nguồn ghi là ngân hàng câu hỏi", all((q.get("sourceFile") or "").startswith("Ngân hàng") for q in done.get("questions", [])), str([q.get("sourceFile") for q in done.get("questions", [])]))
    check("câu sai vào sổ câu sai", psql("select count(*) from review_items where question like 'ZT 2 + 2%'") == "1")

    # --- xóa
    st, _ = gv2.req("DELETE", f"/question-bank/questions/{q2['id']}")
    check("giảng viên khác không xóa được", st == 404, str(st))
    st, _ = gv.req("DELETE", f"/question-bank/questions/{q2['id']}")
    check("giảng viên xóa câu của môn mình", st == 200 and psql("select count(*) from bank_questions where question like 'ZT%'") == "2", str(st))

    # --- xuất CSV danh sách lớp
    st, body, hdr = raw_get(qldt, f"/catalog/students/export?classId={b3d15}")
    text = body.decode("utf-8")
    check("quản lý xuất CSV có BOM và đủ cột", st == 200 and text.startswith("﻿ma_hv,ho_ten,email,ma_lop,khoa_hoc,sdt") and "B3D15001" in text and "attachment" in {k.lower(): v for k, v in hdr.items()}.get("content-disposition", ""), f"{st} {text[:120]!r}")
    st, body, _ = raw_get(qldt, f"/catalog/students/export?classId={uuid.uuid4()}")
    check("lớp không có → 404", st == 404, str(st))
    st, _, _ = raw_get(gv, f"/catalog/students/export?classId={b3d15}")
    check("giảng viên không dùng xuất của quản lý", st == 403, str(st))
    st, body, _ = raw_get(gv, f"/teaching/classes/{b3d15}/export")
    text = body.decode("utf-8")
    check("giảng viên xuất lớp mình dạy, chỉ mã + tên", st == 200 and text.startswith("﻿ma_hv,ho_ten\r\n") and "@" not in text and "B3D15001" in text, f"{st} {text[:120]!r}")
    st, _, _ = raw_get(gv2, f"/teaching/classes/{b3d15}/export")
    check("lớp không thuộc mình → 404", st == 404, str(st))
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
