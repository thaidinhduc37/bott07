"""Kiểm thử kết quả học tập: /grades/*, học kỳ và môn đã đăng ký (/schedules/me/terms, /me/enrollments).

Ghi điểm cho học viên sv.nguyenducanh ở môn CS301 (giảng viên Minh), rồi dọn lại.

    python scripts/test/test_grades.py
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

sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")       # phụ trách CS301
gv2 = login("gv.lehoanganh@hvktcnan.edu.vn")         # không phụ trách môn nào
qldt = login("qldt@hvktcnan.edu.vn")

cs301 = psql("select id from courses where code = 'CS301'")
cls = psql("select id from classes where code = 'B3D15'")
sid = psql("select id from users where email = 'sv.nguyenducanh@hvktcnan.edu.vn'")
other = psql("select id from users where email = 'sv.tranthimai@hvktcnan.edu.vn'")
year, sem = psql(
    f"select academic_year || '|' || semester from schedules where course_id='{cs301}' and class_id='{cls}' limit 1"
).split("|")


def cleanup() -> None:
    psql(f"delete from course_grades where course_id = '{cs301}'")
    psql("delete from notifications where title = 'Có điểm học phần mới'")


def upload(client, path: str, filename: str, content: str) -> tuple[int, dict]:
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n{content}\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        with client.opener.open(req, timeout=60) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def find(items: list[dict], code: str) -> dict:
    return next((c for c in items if c["code"] == code), {})


cleanup()
try:
    # --- học kỳ và môn đã đăng ký
    st, t = sv.req("GET", "/schedules/me/terms")
    check("học kỳ của học viên", st == 200 and len(t.get("terms", [])) >= 1 and t.get("current"), f"{st} {str(t)[:200]}")
    check("học kỳ có khoảng ngày", all(x.get("from") and x.get("to") for x in t.get("terms", [])))
    st, e = sv.req("GET", f"/schedules/me/enrollments?academicYear={year}&semester={sem}")
    cs = find([i["course"] for i in e.get("items", [])], "CS301")
    check("danh sách môn đăng ký có CS301", st == 200 and bool(cs), f"{st} {str(e)[:200]}")
    check("tổng tín chỉ khớp", e.get("totalCredits") == sum(i["course"]["credits"] for i in e.get("items", [])))
    item = next((i for i in e.get("items", []) if i["course"]["code"] == "CS301"), {})
    check("có giảng viên và khung giờ", (item.get("lecturer") or {}).get("name") == "Nguyễn Văn Minh" and len(item.get("slots", [])) >= 1, str(item)[:200])
    st, e2 = sv.req("GET", "/schedules/me/enrollments")
    check("không chỉ định học kỳ → lấy học kỳ hiện tại", st == 200 and e2.get("term") is not None, f"{st}")

    # --- lịch thi theo học kỳ (tab Lịch thi)
    st, x = sv.req("GET", f"/schedules/me/exam-term?academicYear={year}&semester={sem}")
    check("lịch thi theo học kỳ trả 200", st == 200 and "items" in x and x.get("term") is not None, f"{st} {str(x)[:200]}")
    check("số môn thi khớp danh sách", x.get("examCount") == len(x.get("items", [])), str(x)[:200])
    if x.get("items"):
        first = x["items"][0]
        check("mỗi kỳ thi có phòng, ngày, hình thức", all(k in first for k in ("room", "examDate", "formatLabel", "course")), str(first)[:200])
        check("tổng tín chỉ = tổng tín chỉ các môn thi khác nhau",
              x["totalCredits"] == sum({i["course"]["id"]: i["course"]["credits"] for i in x["items"]}.values()), str(x)[:200])

    # --- học viên xem kết quả khi chưa có điểm
    st, r = sv.req("GET", "/grades/me")
    check("kết quả trả 200", st == 200 and isinstance(r.get("terms"), list), f"{st} {str(r)[:200]}")
    term = next((x for x in r.get("terms", []) if x["academicYear"] == year and x["semester"] == sem), {})
    c301 = find(term.get("courses", []), "CS301")
    check("môn trong lịch hiện ra dù chưa có điểm", bool(c301) and c301["total"] is None, str(term)[:200])
    check("chưa có điểm thì điểm trung bình trống", term.get("gpa") is None and r["summary"]["gpa"] is None)

    # --- quyền
    st, _ = sv.req("GET", "/grades/sections")
    check("học viên không vào được danh sách nhập điểm", st == 403, str(st))
    st, _ = gv2.req("GET", f"/grades/sections/roster?courseId={cs301}&classId={cls}&academicYear={year}&semester={sem}")
    check("giảng viên không phụ trách môn → 403", st == 403, str(st))
    st, _ = gv.req("GET", "/grades/me")
    check("giảng viên không dùng /grades/me", st == 403, str(st))

    # --- giảng viên nhập điểm
    st, s = gv.req("GET", "/grades/sections")
    mine = [x for x in s.get("items", []) if x["course"]["code"] == "CS301"]
    check("giảng viên thấy lớp học của môn mình", st == 200 and len(mine) >= 1 and all(x["course"]["code"] == "CS301" for x in s["items"]), str(s)[:200])
    st, ro = gv.req("GET", f"/grades/sections/roster?courseId={cs301}&classId={cls}&academicYear={year}&semester={sem}")
    check("danh sách học viên của lớp", st == 200 and any(x["studentId"] == sid for x in ro.get("students", [])), f"{st} {str(ro)[:200]}")

    body = {"courseId": cs301, "academicYear": year, "semester": sem,
            "items": [{"studentId": sid, "practice": 8, "process": 7, "midterm": 6, "finalExam": 9, "total": 8.1}]}
    st, r1 = gv.req("PUT", "/grades/sections/scores", body)
    check("lưu điểm", st == 200 and r1.get("created") == 1, f"{st} {r1}")
    n = psql(f"select count(*) from notifications where user_id='{sid}' and title='Có điểm học phần mới'")
    check("học viên được thông báo có điểm", int(n or 0) == 1, n)
    st, r2 = gv.req("PUT", "/grades/sections/scores", body)
    check("lưu lại y nguyên → không đổi", st == 200 and r2.get("unchanged") == 1, f"{st} {r2}")
    n = psql(f"select count(*) from notifications where user_id='{sid}' and title='Có điểm học phần mới'")
    check("không thông báo lặp khi điểm không đổi", int(n or 0) == 1, n)

    st, bad = gv.req("PUT", "/grades/sections/scores", {**body, "items": [{"studentId": sid, "total": 11}]})
    check("điểm ngoài 0–10 → 400", st == 400 and bad.get("code") == "INVALID_SCORE", f"{st} {bad}")
    st, bad = gv.req("PUT", "/grades/sections/scores", {**body, "items": [{"studentId": str(uuid.uuid4()), "total": 5}]})
    check("học viên ngoài lớp → 400", st == 400 and bad.get("code") == "NOT_IN_SECTION", f"{st} {bad}")
    st, bad = gv2.req("PUT", "/grades/sections/scores", body)
    check("giảng viên khác không ghi được → 403", st == 403, str(st))
    st, bad = gv.req("PUT", "/grades/sections/scores", {**body, "academicYear": "1999-2000"})
    check("học kỳ không có lịch → 400", st == 400 and bad.get("code") == "NO_SECTION", f"{st} {bad}")

    # --- học viên thấy điểm, điểm trung bình, tín chỉ
    st, r = sv.req("GET", "/grades/me")
    term = next((x for x in r["terms"] if x["academicYear"] == year and x["semester"] == sem), {})
    c301 = find(term.get("courses", []), "CS301")
    check("điểm hiện đúng", c301.get("total") == 8.1 and c301.get("practice") == 8.0 and c301.get("passed") is True, str(c301))
    credits = c301.get("credits", 0)
    check("điểm trung bình học kỳ = điểm duy nhất", term.get("gpa") == 8.1, str(term.get("gpa")))
    check("tín chỉ tích lũy tính môn đạt", r["summary"]["creditsEarned"] == credits and r["summary"]["creditsStudied"] == credits, str(r["summary"]))

    # --- điểm không đạt: không tích lũy
    st, _ = qldt.req("PUT", "/grades/sections/scores", {**body, "items": [{"studentId": sid, "total": 4.5}]})
    st, r = sv.req("GET", "/grades/me")
    check("môn không đạt: có điểm trung bình nhưng không tích lũy", r["summary"]["creditsEarned"] == 0 and r["summary"]["gpa"] == 4.5 and r["summary"]["gpaEarned"] is None, str(r["summary"]))

    # --- nhập CSV (quản lý)
    head = "ma_hv,ma_mon,nam_hoc,hoc_ky,th,qt,gk,ck,diem_hp,ghi_chu\n"
    code = psql(f"select student_code from student_profiles where user_id='{sid}'")
    st, d = upload(qldt, "/grades/import?dryRun=true", "diem.csv", head + f"{code},CS301,{year},{sem},7,7,7,7,7.5,\n")
    check("nhập thử hợp lệ, chưa ghi", st == 200 and d.get("validRows") == 1 and d.get("accepted") is False, f"{st} {d}")
    check("nhập thử không ghi gì", psql(f"select total from course_grades where student_id='{sid}' and course_id='{cs301}'") == "4.5")
    st, d = upload(qldt, "/grades/import", "diem.csv", head + f"KHONGCO,CS301,{year},{sem},,,,,5,\n{code},CS301,{year},{sem},,,,,12,\n")
    check("CSV có dòng lỗi → báo từng dòng, không ghi", st == 200 and len(d.get("errors", [])) == 2 and d.get("accepted") is False, f"{st} {d}")
    st, d = upload(qldt, "/grades/import", "diem.csv", head + f"{code},CS301,{year},{sem},7,7,7,7,7.5,Cải thiện\n")
    check("nhập CSV hợp lệ", st == 200 and d.get("accepted") is True and d.get("updated") == 1, f"{st} {d}")
    check("điểm sau nhập CSV", psql(f"select total from course_grades where student_id='{sid}' and course_id='{cs301}'") == "7.5")
    st, d = upload(qldt, "/grades/import", "x.csv", "a,b\n1,2\n")
    check("thiếu cột bắt buộc → 400", st == 400 and d.get("code") == "BAD_HEADER", f"{st} {d}")
    st, d = upload(gv, "/grades/import", "diem.csv", head)
    check("giảng viên không nhập CSV được", st == 403, str(st))
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
