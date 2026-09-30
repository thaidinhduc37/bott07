"""Kiểm thử /catalog/* — quản lý Lớp, Môn học (gán giảng viên), gán học viên vào lớp.

Dữ liệu thử có tiền tố `ZT` và được dọn lại ở cuối (kể cả khi có lỗi).

    python scripts/test/test_catalog.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

qldt = login("qldt@hvktcnan.edu.vn")
sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")

STUDENT_EMAIL = "sv.tranthimai@hvktcnan.edu.vn"
student_id = psql(f"select id from users where email = '{STUDENT_EMAIL}'")
orig_class = psql(f"select coalesce(class_id::text,'') from student_profiles where user_id = '{student_id}'")


def cleanup() -> None:
    psql("delete from notifications where title like '%ZT%' or body like '%ZT%'")
    psql("update courses set lecturer_id = NULL where code like 'ZT%'")
    psql("delete from courses where code like 'ZT%'")
    if orig_class:
        psql(f"update student_profiles set class_id = '{orig_class}' where user_id = '{student_id}'")
    else:
        psql(f"update student_profiles set class_id = NULL where user_id = '{student_id}'")
    psql("delete from classes where code like 'ZT%'")


cleanup()
try:
    # --- quyền
    st, _ = sv.req("GET", "/catalog/classes")
    check("học viên bị từ chối", st == 403, str(st))
    st, _ = gv.req("GET", "/catalog/courses")
    check("giảng viên bị từ chối", st == 403, str(st))

    # --- lớp
    st, c = qldt.req("POST", "/catalog/classes", {"code": "zt01", "name": "Lớp thử", "faculty": "Khoa thử", "cohortYear": 2026})
    check("tạo lớp", st in (200, 201) and c.get("code") == "ZT01", f"{st} {c}")
    class_id = c.get("id", "")
    check("lớp mới có 0 học viên", c.get("studentCount") == 0 and c.get("sessionCount") == 0, str(c))
    st, c2 = qldt.req("POST", "/catalog/classes", {"code": "ZT01", "name": "Trùng"})
    check("trùng mã lớp → 409", st == 409 and c2.get("code") == "CLASS_CODE_TAKEN", f"{st} {c2}")
    st, c = qldt.req("PATCH", f"/catalog/classes/{class_id}", {"name": "Lớp thử đổi tên", "faculty": None})
    check("sửa lớp + xóa khoa", st == 200 and c.get("name") == "Lớp thử đổi tên" and c.get("faculty") is None, f"{st} {c}")
    st, lst = qldt.req("GET", "/catalog/classes")
    check("danh sách có lớp mới", any(x["code"] == "ZT01" for x in lst.get("items", [])))
    st, r = qldt.req("PATCH", "/catalog/classes/khong-phai-uuid", {"name": "x"})
    check("id sai định dạng → 404 (không 500)", st == 404, f"{st} {r}")

    # --- môn + giảng viên
    st, lects = qldt.req("GET", "/catalog/lecturers")
    minh = next((x for x in lects.get("items", []) if x["email"] == "gv.nguyenvanminh@hvktcnan.edu.vn"), None)
    check("danh sách giảng viên có GV Minh", minh is not None, str(lects)[:200])
    st, co = qldt.req("POST", "/catalog/courses", {"code": "zt101", "name": "Môn thử", "credits": 3, "lecturerId": minh["id"] if minh else None})
    check("tạo môn kèm giảng viên", st in (200, 201) and co.get("lecturer", {}).get("email") == "gv.nguyenvanminh@hvktcnan.edu.vn", f"{st} {co}")
    course_id = co.get("id", "")
    st, bad = qldt.req("POST", "/catalog/courses", {"code": "ZT102", "name": "Sai GV", "credits": 3, "lecturerId": student_id})
    check("gán người không phải giảng viên → 400", st == 400 and bad.get("code") == "INVALID_LECTURER", f"{st} {bad}")
    st, dup = qldt.req("POST", "/catalog/courses", {"code": "ZT101", "name": "Trùng", "credits": 2})
    check("trùng mã môn → 409", st == 409 and dup.get("code") == "COURSE_CODE_TAKEN", f"{st} {dup}")
    st, co = qldt.req("PATCH", f"/catalog/courses/{course_id}", {"lecturerId": None, "credits": 4})
    check("bỏ gán giảng viên + sửa tín chỉ", st == 200 and co.get("lecturer") is None and co.get("credits") == 4, f"{st} {co}")
    st, co = qldt.req("PATCH", f"/catalog/courses/{course_id}", {"lecturerId": minh["id"] if minh else None})
    n = psql("select count(*) from notifications n join users u on u.id=n.user_id "
             "where u.email='gv.nguyenvanminh@hvktcnan.edu.vn' and n.created_at > now() - interval '1 minute'")
    check("giảng viên được thông báo khi phân công", int(n or 0) >= 1, n)

    # --- học viên ↔ lớp
    st, r = qldt.req("PUT", f"/catalog/students/{student_id}/class", {"classId": class_id})
    check("xếp học viên vào lớp", st == 200 and (r.get("class") or {}).get("code") == "ZT01", f"{st} {r}")
    st, lst = qldt.req("GET", f"/catalog/students?classId={class_id}")
    check("lọc học viên theo lớp", lst.get("total") == 1 and lst["items"][0]["id"] == student_id, str(lst)[:200])
    st, lst = qldt.req("GET", "/catalog/students?search=TRAN")
    check("tìm học viên không phân biệt hoa thường", any(x["id"] == student_id for x in lst.get("items", [])), str(lst)[:200])
    st, cls = qldt.req("GET", "/catalog/classes")
    zt = next((x for x in cls["items"] if x["code"] == "ZT01"), {})
    check("studentCount cập nhật", zt.get("studentCount") == 1, str(zt))

    st, r = qldt.req("DELETE", f"/catalog/classes/{class_id}")
    check("xóa lớp còn học viên → 409", st == 409 and r.get("code") == "CLASS_IN_USE", f"{st} {r}")

    qldt.req("PUT", f"/catalog/students/{student_id}/class", {"classId": None})
    st, r = qldt.req("POST", "/catalog/students/assign-class", {"classId": class_id, "userIds": [student_id, minh["id"] if minh else student_id]})
    check("gán hàng loạt: bỏ qua người không phải học viên", st == 200 and r.get("updated") == 1 and r.get("skipped") == 1, f"{st} {r}")

    st, r = qldt.req("PUT", f"/catalog/students/{student_id}/class", {"classId": None})
    check("rút học viên khỏi lớp", st == 200 and r.get("class") is None, f"{st} {r}")
    st, lst = qldt.req("GET", "/catalog/students?unassigned=true")
    check("lọc học viên chưa có lớp", any(x["id"] == student_id for x in lst.get("items", [])), str(lst)[:200])

    st, r = qldt.req("DELETE", f"/catalog/classes/{class_id}")
    check("xóa lớp trống", st == 200, f"{st} {r}")
    st, r = qldt.req("DELETE", f"/catalog/courses/{course_id}")
    check("xóa môn trống", st == 200, f"{st} {r}")

    n = psql("select count(*) from audit_logs where action in ('CLASS_CREATE','COURSE_CREATE','STUDENT_CLASS_ASSIGN') "
             "and created_at > now() - interval '5 minutes'")
    check("có ghi audit", int(n or 0) >= 3, n)
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
