"""Kiểm thử sửa lịch: kiểm tra trùng (lớp / phòng / giảng viên), PATCH, khả dụng, CRUD ca thi.

Dùng ngày xa (2031-03-03) và phòng `ZT-*` để không đụng lịch thật; dọn lại ở cuối.

    python scripts/test/test_schedule_edit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

qldt = login("qldt@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")

DAY = "2031-03-03"
cls_a = psql("select id from classes where code = 'B3D15'")
cls_b = psql("select id from classes where code = 'DS1'")
cs301 = psql("select id from courses where code = 'CS301'")   # có giảng viên Minh
cs302 = psql("select id from courses where code = 'CS302'")   # chưa có giảng viên


def cleanup() -> None:
    psql("delete from schedules where room ilike 'zt-%'")
    psql("delete from exam_schedules where room ilike 'zt-%'")
    psql("delete from notifications where created_at > now() - interval '30 minutes' and title like '%2031%'")


def session(cls: str, course: str, start: str, end: str, room: str, **extra) -> tuple[int, dict]:
    body = {
        "classId": cls, "courseId": course, "academicYear": "2030-2031", "semester": "1",
        "sessionDate": DAY, "startPeriod": 1, "endPeriod": 3, "startTime": start, "endTime": end,
        "room": room, "sessionType": "LY_THUYET",
    }
    body.update(extra)
    return qldt.req("POST", "/schedules", body)


def kinds(resp: dict) -> set[str]:
    return {c.get("kind") for c in resp.get("conflicts", [])}


cleanup()
try:
    # --- tạo buổi hợp lệ, tên người dạy tự điền từ giảng viên của môn
    st, a = session(cls_a, cs301, "09:00", "10:30", "ZT-P1")
    check("tạo buổi hợp lệ", st in (200, 201), f"{st} {a}")
    check("tự điền tên người dạy", a.get("instructor") == "Nguyễn Văn Minh", str(a.get("instructor")))
    a_id = a.get("id", "")

    # --- trùng
    st, r = session(cls_b, cs301, "10:00", "11:30", "ZT-P2")
    check("trùng giảng viên → 409", st == 409 and r.get("code") == "SCHEDULE_CONFLICT" and "LECTURER" in kinds(r), f"{st} {r}")
    check("lỗi trùng có chi tiết buổi trùng", bool(r.get("conflicts")) and r["conflicts"][0].get("course", {}).get("code") == "CS301", str(r)[:300])
    st, r = session(cls_b, cs302, "09:30", "10:30", "zt-p1 ")
    check("trùng phòng (không phân biệt hoa thường/khoảng trắng) → 409", st == 409 and "ROOM" in kinds(r), f"{st} {r}")
    st, r = session(cls_a, cs302, "10:00", "11:00", "ZT-P3")
    check("trùng lớp → 409", st == 409 and "CLASS" in kinds(r), f"{st} {r}")
    st, r = session(cls_a, cs301, "10:30", "12:00", "ZT-P1")
    check("liền kề (10:30 = giờ kết thúc buổi trước) không tính là trùng", st in (200, 201), f"{st} {r}")
    b_id = r.get("id", "")

    # --- phòng "Chưa xếp phòng" không được coi là một phòng chung
    st, r1 = session(cls_b, cs302, "14:00", "15:00", "Chưa xếp phòng")
    check("tạo buổi chưa xếp phòng", st in (200, 201), f"{st} {r1}")
    st, r2 = session(cls_a, cs302, "14:00", "15:00", "Chưa xếp phòng")
    check("hai buổi cùng chưa xếp phòng không báo trùng phòng", st in (200, 201) or "ROOM" not in kinds(r2), f"{st} {str(r2)[:200]}")
    psql(f"delete from schedules where session_date = '{DAY}' and room = 'Chưa xếp phòng'")

    # --- sửa
    st, r = qldt.req("PATCH", f"/schedules/{b_id}", {"startTime": "09:30"})
    check("PATCH gây trùng → 409", st == 409 and r.get("code") == "SCHEDULE_CONFLICT", f"{st} {r}")
    st, r = qldt.req("PATCH", f"/schedules/{b_id}", {"startTime": "13:00", "endTime": "14:30"})
    check("PATCH sang giờ trống → 200", st == 200, f"{st} {r}")
    st, r = qldt.req("PATCH", f"/schedules/{a_id}", {"room": "ZT-P1"})
    check("sửa không đổi gì quan trọng không tự trùng với chính nó", st == 200, f"{st} {r}")

    # --- khả dụng
    q = f"date={DAY}&startTime=09:15&endTime=10:00"
    st, av = qldt.req("GET", f"/schedules/availability?{q}")
    check("availability trả 200", st == 200, f"{st} {av}")
    room = next((x for x in av.get("rooms", []) if x["room"] == "ZT-P1"), {})
    check("phòng ZT-P1 báo bận", room.get("busy") is True and room.get("by") is not None, str(room))
    minh = next((x for x in av.get("lecturers", []) if x["fullName"] == "Nguyễn Văn Minh"), {})
    check("giảng viên Minh báo bận", minh.get("busy") is True, str(minh))
    st, av = qldt.req("GET", f"/schedules/availability?{q}&excludeId={a_id}")
    room = next((x for x in av.get("rooms", []) if x["room"] == "ZT-P1"), {})
    check("loại trừ chính buổi đang sửa → hết bận", room.get("busy") is False, str(room))
    st, av = qldt.req("GET", f"/schedules/availability?date={DAY}&startTime=16:00&endTime=17:00")
    room = next((x for x in av.get("rooms", []) if x["room"] == "ZT-P1"), {})
    check("giờ khác thì phòng rảnh", room.get("busy") is False, str(room))
    st, _ = qldt.req("GET", f"/schedules/availability?date={DAY}&startTime=10:00&endTime=09:00")
    check("giờ ngược → 400", st == 400, str(st))

    # --- ca thi
    exam = {
        "classId": cls_a, "courseId": cs302, "academicYear": "2030-2031", "semester": "1",
        "examDate": DAY, "startTime": "15:00", "durationMinutes": 90, "room": "ZT-E1", "building": "Nhà A",
        "candidateCount": 30, "chiefProctor": "Thầy A",
    }
    st, e = qldt.req("POST", "/schedules/exams", exam)
    check("tạo ca thi", st in (200, 201) and e.get("room") == "ZT-E1", f"{st} {e}")
    e_id = e.get("id", "")
    st, r = qldt.req("POST", "/schedules/exams", {**exam, "classId": cls_b, "startTime": "15:30"})
    check("ca thi trùng phòng → 409", st == 409 and "ROOM" in kinds(r), f"{st} {r}")
    st, r = qldt.req("PATCH", f"/schedules/exams/{e_id}", {"durationMinutes": 120, "note": "đổi"})
    check("sửa ca thi", st == 200 and r.get("durationMinutes") == 120, f"{st} {r}")
    st, r = qldt.req("DELETE", f"/schedules/exams/{e_id}")
    check("xóa ca thi", st == 200, f"{st} {r}")

    # --- quyền
    st, _ = gv.req("POST", "/schedules", {"classId": cls_a, "courseId": cs301})
    check("giảng viên không được tạo buổi", st in (400, 403, 422) and st != 200, str(st))
    st, _ = gv.req("POST", "/schedules/exams", exam)
    check("giảng viên không được tạo ca thi", st == 403, str(st))
    st, _ = gv.req("GET", f"/schedules/availability?{q}")
    check("giảng viên không xem availability", st == 403, str(st))

    st, _ = qldt.req("DELETE", f"/schedules/{a_id}")
    check("xóa buổi", st == 200, str(st))
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
