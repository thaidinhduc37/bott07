"""Kiểm thử /faculties/* — khoa, trưởng khoa, phân công giảng viên trong phạm vi khoa.

Dữ liệu thử có tiền tố `ZT`, dọn lại ở cuối (kể cả khi lỗi).

    python scripts/test/test_faculties.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

qldt = login("qldt@hvktcnan.edu.vn")
head = login("khoa@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")

head_id = psql("select id from users where email = 'khoa@hvktcnan.edu.vn'")
minh_id = psql("select id from users where email = 'gv.nguyenvanminh@hvktcnan.edu.vn'")
hoang_id = psql("select id from users where email = 'gv.lehoanganh@hvktcnan.edu.vn'")
sv_id = psql("select id from users where email = 'sv.tranthimai@hvktcnan.edu.vn'")


def cleanup() -> None:
    psql("update courses set lecturer_id = NULL, faculty_id = NULL where code like 'ZT%'")
    psql("delete from courses where code like 'ZT%'")
    psql("update users set faculty_id = NULL where faculty_id in (select id from faculties where code like 'ZT%')")
    psql("update classes set faculty_id = NULL where faculty_id in (select id from faculties where code like 'ZT%')")
    psql("update faculties set head_id = NULL where code like 'ZT%'")
    psql("delete from faculties where code like 'ZT%'")
    psql("delete from classes where code like 'ZT%'")
    psql("delete from notifications where created_at > now() - interval '30 minutes' and body like '%ZT%'")


cleanup()
try:
    # --- quyền
    st, _ = gv.req("GET", "/faculties")
    check("giảng viên không xem được danh sách khoa", st == 403, str(st))
    st, _ = head.req("POST", "/faculties", {"code": "ZTX", "name": "Khoa X"})
    check("trưởng khoa không tạo được khoa", st == 403, str(st))

    # --- CRUD khoa
    st, f1 = qldt.req("POST", "/faculties", {"code": "zt1", "name": "Khoa thử 1", "headId": head_id})
    check("tạo khoa kèm trưởng khoa", st in (200, 201) and f1.get("code") == "ZT1" and (f1.get("head") or {}).get("id") == head_id, f"{st} {f1}")
    fid = f1.get("id", "")
    st, r = qldt.req("POST", "/faculties", {"code": "ZT1", "name": "Tên khác"})
    check("trùng mã khoa → 409", st == 409 and r.get("code") == "FACULTY_CODE_TAKEN", f"{st} {r}")
    st, r = qldt.req("POST", "/faculties", {"code": "ZT2", "name": "khoa THỬ 1"})
    check("trùng tên (không phân biệt hoa thường) → 409", st == 409 and r.get("code") == "FACULTY_NAME_TAKEN", f"{st} {r}")
    st, r = qldt.req("POST", "/faculties", {"code": "ZT3", "name": "Sai trưởng khoa", "headId": sv_id})
    check("trưởng khoa không đúng vai trò → 400", st == 400 and r.get("code") == "INVALID_HEAD", f"{st} {r}")
    check("đặt trưởng khoa thì người đó thuộc khoa", psql(f"select faculty_id::text from users where id='{head_id}'") == fid)

    # --- trưởng khoa chỉ thấy khoa mình
    st, r = qldt.req("POST", "/faculties", {"code": "ZT4", "name": "Khoa thử 4"})
    other = r.get("id", "")
    st, lst = head.req("GET", "/faculties")
    check("trưởng khoa chỉ thấy khoa của mình", st == 200 and [x["code"] for x in lst.get("items", [])] == ["ZT1"], str(lst)[:200])
    st, _ = head.req("GET", f"/faculties/{other}/overview")
    check("khoa khác → 404", st == 404, str(st))
    st, ov = head.req("GET", f"/faculties/{fid}/overview")
    check("trưởng khoa xem tổng quan khoa mình", st == 200 and ov.get("faculty", {}).get("code") == "ZT1", f"{st} {str(ov)[:200]}")

    # --- giảng viên vào khoa
    st, cand = head.req("GET", "/faculties/lecturer-candidates")
    check("có ứng viên giảng viên", st == 200 and any(x["id"] == minh_id for x in cand.get("items", [])), str(cand)[:200])
    st, r = head.req("PUT", f"/faculties/{fid}/lecturers/{minh_id}")
    check("trưởng khoa đưa giảng viên vào khoa", st == 200, f"{st} {r}")
    st, r = head.req("PUT", f"/faculties/{fid}/lecturers/{sv_id}")
    check("không phải giảng viên → 400/409", st in (400, 409), f"{st} {r}")
    st, r = qldt.req("PUT", f"/faculties/{other}/lecturers/{minh_id}")
    check("giảng viên khoa khác: quản lý đào tạo vẫn chuyển được", st == 200, f"{st} {r}")
    st, r = qldt.req("PUT", f"/faculties/{fid}/lecturers/{minh_id}")

    # --- môn + phân công
    st, co = qldt.req("POST", "/catalog/courses", {"code": "zt901", "name": "Môn thử khoa", "credits": 3, "facultyId": fid})
    check("tạo môn thuộc khoa", st in (200, 201) and co.get("facultyId") == fid, f"{st} {co}")
    cid = co.get("id", "")
    st, r = head.req("PUT", f"/faculties/{fid}/courses/{cid}", {"lecturerId": minh_id})
    check("trưởng khoa phân công giảng viên của khoa", st == 200 and (r.get("lecturer") or {}).get("id") == minh_id, f"{st} {r}")
    st, r = head.req("PUT", f"/faculties/{fid}/courses/{cid}", {"lecturerId": hoang_id})
    check("giảng viên ngoài khoa: trưởng khoa bị từ chối", st in (400, 403, 409), f"{st} {r}")
    st, ov = head.req("GET", f"/faculties/{fid}/overview")
    check("tổng quan phản ánh môn và giảng viên", any(c["id"] == cid for c in ov.get("courses", [])) and any(l["id"] == minh_id for l in ov.get("lecturers", [])), str(ov)[:300])
    st, r = head.req("DELETE", f"/faculties/{fid}/lecturers/{minh_id}")
    check("bỏ giảng viên khỏi khoa → bỏ phân công môn", st == 200 and r.get("unassignedCourses") == 1, f"{st} {r}")
    check("môn không còn giảng viên", psql(f"select coalesce(lecturer_id::text,'') from courses where id='{cid}'") == "")

    # --- lớp gắn khoa, đổi tên đồng bộ
    st, cl = qldt.req("POST", "/catalog/classes", {"code": "ZTL1", "name": "Lớp thử", "facultyId": fid})
    check("lớp gắn khoa; tên khoa dạng chữ đồng bộ", st in (200, 201) and cl.get("facultyId") == fid and cl.get("faculty") == "Khoa thử 1", f"{st} {cl}")
    st, r = qldt.req("PATCH", f"/faculties/{fid}", {"name": "Khoa thử 1 đổi tên"})
    check("đổi tên khoa", st == 200 and r.get("name") == "Khoa thử 1 đổi tên", f"{st} {r}")
    st, lst = qldt.req("GET", "/catalog/classes")
    zt = next((x for x in lst.get("items", []) if x["code"] == "ZTL1"), {})
    check("tên khoa của lớp đổi theo", zt.get("faculty") == "Khoa thử 1 đổi tên", str(zt))

    st, r = qldt.req("DELETE", f"/faculties/{fid}")
    check("xóa khoa còn lớp/môn → 409", st == 409 and r.get("code") == "FACULTY_IN_USE", f"{st} {r}")
    st, r = qldt.req("DELETE", f"/faculties/{other}")
    check("xóa khoa trống", st == 200, f"{st} {r}")
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
