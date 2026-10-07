"""Kiểm thử "Lớp của tôi" của giảng viên: /teaching/classes (chỉ đọc, đúng phạm vi môn mình phụ trách).

    python scripts/test/test_teaching.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check, login, psql  # noqa: E402

gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")   # phụ trách CS301
gv2 = login("gv.lehoanganh@hvktcnan.edu.vn")     # không phụ trách môn nào
sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
qldt = login("qldt@hvktcnan.edu.vn")

b3d15 = psql("select id from classes where code = 'B3D15'")

st, d = gv.req("GET", "/teaching/classes")
items = d.get("items", [])
check("giảng viên xem được danh sách lớp", st == 200 and len(items) >= 1, f"{st} {str(d)[:200]}")
mine = next((c for c in items if c["id"] == b3d15), None)
check("có lớp B3D15 cùng môn CS301", bool(mine) and any(c["code"] == "CS301" for c in mine["courses"]), str(mine)[:200])
check("sĩ số khớp CSDL", bool(mine) and mine["studentCount"] == int(psql(f"select count(*) from student_profiles where class_id='{b3d15}'")))

# Mọi lớp trả về đều có lịch môn của giảng viên này.
own = int(psql(
    "select count(distinct s.class_id) from schedules s join courses c on c.id = s.course_id "
    "join users u on u.id = c.lecturer_id where u.email = 'gv.nguyenvanminh@hvktcnan.edu.vn'"
))
check("số lớp khớp lịch của môn mình phụ trách", len(items) == own, f"{len(items)} != {own}")

st, d = gv.req("GET", f"/teaching/classes/{b3d15}")
check("chi tiết lớp trả 200", st == 200 and d.get("class", {}).get("code") == "B3D15", f"{st} {str(d)[:200]}")
check("danh sách học viên chỉ có mã và họ tên", all(set(s) == {"studentCode", "fullName"} for s in d.get("students", [])) and len(d.get("students", [])) >= 1)
check("buổi sắp tới đều thuộc môn của mình", all(u["courseCode"] == "CS301" for u in d.get("upcoming", [])), str(d.get("upcoming"))[:200])

# Phạm vi: giảng viên khác, lớp không tồn tại, id sai định dạng.
st, d = gv2.req("GET", "/teaching/classes")
check("giảng viên không có môn → danh sách rỗng", st == 200 and d.get("items") == [], f"{st} {str(d)[:200]}")
st, _ = gv2.req("GET", f"/teaching/classes/{b3d15}")
check("lớp không thuộc phạm vi → 404", st == 404, str(st))
st, _ = gv.req("GET", f"/teaching/classes/{uuid.uuid4()}")
check("lớp không tồn tại → 404", st == 404, str(st))
st, _ = gv.req("GET", "/teaching/classes/khong-hop-le")
check("id sai định dạng → 404", st == 404, str(st))

# Vai trò khác không dùng được.
st, _ = sv.req("GET", "/teaching/classes")
check("học viên bị chặn", st == 403, str(st))
st, _ = qldt.req("GET", "/teaching/classes")
check("quản lý đào tạo dùng trang quản lý, không dùng /teaching", st == 403, str(st))

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
