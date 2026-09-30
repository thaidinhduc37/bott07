"""Kiểm thử /rooms/* — danh mục phòng, lịch phòng, tích hợp availability và kiểm tra sức chứa.

Dùng ngày xa (2031-04-07) và phòng `ZT-*`, dọn lại ở cuối.

    python scripts/test/test_rooms.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

qldt = login("qldt@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")
sv = login("sv.nguyenducanh@hvktcnan.edu.vn")

DAY = "2031-04-07"
cls_a = psql("select id from classes where code = 'B3D15'")
cs302 = psql("select id from courses where code = 'CS302'")


def cleanup() -> None:
    psql("delete from schedules where room ilike 'zt-%'")
    psql("delete from exam_schedules where room ilike 'zt-%'")
    psql("delete from rooms where code ilike 'zt-%'")


cleanup()
try:
    st, _ = sv.req("GET", "/rooms")
    check("học viên không xem được danh mục phòng", st == 403, str(st))
    st, lst = gv.req("GET", "/rooms")
    check("giảng viên xem được danh mục", st == 200 and isinstance(lst.get("items"), list), f"{st}")
    st, _ = gv.req("POST", "/rooms", {"code": "ZT-X"})
    check("giảng viên không tạo được phòng", st == 403, str(st))

    st, r = qldt.req("POST", "/rooms", {"code": "ZT-R1", "building": "Nhà Z", "capacity": 5, "kind": "Lý thuyết"})
    check("tạo phòng", st in (200, 201) and r.get("capacity") == 5 and r.get("isActive") is True and r.get("usageCount") == 0, f"{st} {r}")
    rid = r.get("id", "")
    st, r = qldt.req("POST", "/rooms", {"code": "zt-r1", "building": "nhà z"})
    check("trùng (mã, tòa) không phân biệt hoa thường → 409", st == 409 and r.get("code") == "ROOM_TAKEN", f"{st} {r}")
    st, r = qldt.req("POST", "/rooms", {"code": "ZT-R2", "building": "Nhà Z", "capacity": 100})
    rid2 = r.get("id", "")

    # --- availability dùng danh mục
    st, av = qldt.req("GET", f"/schedules/availability?date={DAY}&startTime=08:00&endTime=09:00")
    room = next((x for x in av.get("rooms", []) if x["room"] == "ZT-R1"), {})
    check("phòng trong danh mục xuất hiện, kèm sức chứa", room.get("registered") is True and room.get("capacity") == 5 and room.get("busy") is False, str(room))

    # --- sức chứa
    exam = {
        "classId": cls_a, "courseId": cs302, "academicYear": "2030-2031", "semester": "1", "examDate": DAY,
        "startTime": "08:00", "durationMinutes": 60, "room": "ZT-R1", "building": "Nhà Z", "candidateCount": 30,
    }
    st, r = qldt.req("POST", "/schedules/exams", exam)
    check("thí sinh vượt sức chứa → 400 ROOM_TOO_SMALL", st == 400 and r.get("code") == "ROOM_TOO_SMALL", f"{st} {r}")
    st, r = qldt.req("POST", "/schedules/exams", {**exam, "room": "ZT-R2"})
    check("phòng đủ chỗ → tạo được", st in (200, 201), f"{st} {r}")
    exam_id = r.get("id", "")
    st, r = qldt.req("POST", "/schedules/exams", {**exam, "room": "ZT-Chua-Co", "building": None, "startTime": "13:00"})
    check("phòng ngoài danh mục không bị kiểm tra sức chứa", st in (200, 201), f"{st} {r}")

    # --- usage, khóa đổi tên, lịch phòng
    st, r = qldt.req("GET", "/rooms?activeOnly=false&search=ZT-R2")
    row = next((x for x in r.get("items", []) if x["code"] == "ZT-R2"), {})
    check("usageCount đếm ca thi", row.get("usageCount") == 1, str(row))
    st, r = qldt.req("PATCH", f"/rooms/{rid2}", {"code": "ZT-R2B"})
    check("đổi mã phòng đang có lịch → 409", st == 409 and r.get("code") == "ROOM_IN_USE", f"{st} {r}")
    st, r = qldt.req("PATCH", f"/rooms/{rid2}", {"capacity": 120, "note": "đã sửa"})
    check("đổi sức chứa/ghi chú luôn được", st == 200 and r.get("capacity") == 120, f"{st} {r}")
    st, r = qldt.req("DELETE", f"/rooms/{rid2}")
    check("xóa phòng đang có lịch → 409", st == 409 and r.get("code") == "ROOM_IN_USE", f"{st} {r}")
    st, tt = qldt.req("GET", f"/rooms/{rid2}/timetable?from={DAY}&to={DAY}")
    check("lịch phòng liệt kê ca thi", st == 200 and len(tt.get("items", [])) == 1 and tt["items"][0]["entryKind"] == "EXAM", f"{st} {str(tt)[:200]}")
    st, _ = qldt.req("GET", f"/rooms/{rid2}/timetable?from=2031-01-01&to=2031-12-31")
    check("khoảng quá 62 ngày → 400", st == 400, str(st))

    # --- ngừng sử dụng
    st, r = qldt.req("PATCH", f"/rooms/{rid}", {"isActive": False})
    check("ngừng sử dụng phòng", st == 200 and r.get("isActive") is False, f"{st} {r}")
    st, av = qldt.req("GET", f"/schedules/availability?date={DAY}&startTime=16:00&endTime=17:00")
    check("phòng ngừng sử dụng không xuất hiện trong availability", not any(x["room"] == "ZT-R1" for x in av.get("rooms", [])), "")
    st, r = qldt.req("GET", "/rooms?activeOnly=true")
    check("activeOnly ẩn phòng ngừng sử dụng", not any(x["code"] == "ZT-R1" for x in r.get("items", [])), "")

    qldt.req("DELETE", f"/schedules/exams/{exam_id}")
    st, r = qldt.req("DELETE", f"/rooms/{rid}")
    check("xóa phòng chưa dùng", st == 200, f"{st} {r}")
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
