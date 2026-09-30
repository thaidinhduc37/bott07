"""Kiểm thử ghi chú/yêu cầu của giảng viên cho buổi học và ca thi.

Giảng viên CS301 (gv.nguyenvanminh) ghi yêu cầu; học viên lớp B3D15 thấy trong
thời khóa biểu và nhận thông báo; người không phụ trách môn bị chặn. Dọn dữ liệu
thử bằng psql trong container `sa-postgres-dev`.

    python scripts/test/test_lecturer_note.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import Client, check, login, psql  # noqa: E402

sv = login("sv.nguyenducanh@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")      # phụ trách CS301
gv2 = login("gv.lehoanganh@hvktcnan.edu.vn")        # không phụ trách môn nào
qldt = login("qldt@hvktcnan.edu.vn")

row = psql(
    "select s.id, s.session_date from schedules s join courses c on c.id = s.course_id "
    "where c.code = 'CS301' order by s.starts_at limit 1"
)
sid, sdate = row.split("|")
erow = psql("select e.id, e.exam_date from exam_schedules e join courses c on c.id = e.course_id where c.code = 'CS301' limit 1")
eid, edate = erow.split("|")
other = psql(
    "select s.id from schedules s join courses c on c.id = s.course_id where c.code <> 'CS301' limit 1"
)
sv_uid = psql("select id from users where email = 'sv.nguyenducanh@hvktcnan.edu.vn'")
psql(f"update schedules set lecturer_note = null, lecturer_note_updated_at = null, lecturer_note_by_id = null where id in ('{sid}', '{other}')")
psql(f"update exam_schedules set lecturer_note = null, lecturer_note_updated_at = null, lecturer_note_by_id = null where id = '{eid}'")
psql(f"delete from notifications where link_to like '%{sid}%' or link_to like '%{eid}%'")


def my_week(day: str) -> dict:
    return sv.req("GET", f"/schedules/me?from={day}&to={day}")[1]


try:
    print("\n[1] Thời khóa biểu học viên có đủ thông tin chi tiết")
    tt = my_week(sdate)
    s = next((x for x in tt["sessions"] if x["id"] == sid), None)
    check("buổi CS301 có trong lịch học viên", s is not None)
    check("có kind = SESSION, nhãn loại buổi và trạng thái",
          s and s["kind"] == "SESSION" and s["sessionTypeLabel"] and s["statusLabel"], str(s)[:200])
    check("có giảng viên phụ trách môn (tên + email)", s and s["lecturer"] and s["lecturer"]["name"] == "Nguyễn Văn Minh", str(s and s["lecturer"]))
    ex = next((x for x in my_week(edate)["exams"] if x["id"] == eid), None)
    check("ca thi có kind = EXAM và nhãn hình thức thi", ex and ex["kind"] == "EXAM" and ex["formatLabel"], str(ex)[:200])

    print("\n[2] Phân quyền ghi yêu cầu")
    check("học viên -> 403", sv.req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": "x"})[0] == 403)
    check("chưa đăng nhập -> 401", Client().req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": "x"})[0] == 401)
    check("giảng viên không phụ trách môn -> 403", gv2.req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": "x"})[0] == 403)
    check("giảng viên CS301 sửa buổi môn khác -> 403", gv.req("PUT", f"/schedules/sessions/{other}/lecturer-note", {"note": "x"})[0] == 403)
    check("id không tồn tại -> 404", gv.req("PUT", f"/schedules/sessions/{uuid.uuid4()}/lecturer-note", {"note": "x"})[0] == 404)
    check("quá 4000 ký tự -> 400", gv.req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": "a" * 4001})[0] == 400)

    print("\n[3] Giảng viên ghi yêu cầu — học viên thấy và được báo")
    note = "Mang laptop đã cài Python 3.11. Đọc trước chương 3 giáo trình Học máy."
    s_code, r = gv.req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": note})
    check("200 + trả lại ghi chú, người sửa, thời điểm",
          s_code == 200 and r["lecturerNote"]["text"] == note and r["lecturerNote"]["updatedBy"] == "Nguyễn Văn Minh"
          and r["lecturerNote"]["updatedAt"], f"{s_code} {r}")
    s2 = next(x for x in my_week(sdate)["sessions"] if x["id"] == sid)
    check("học viên thấy yêu cầu trong thời khóa biểu", s2["lecturerNote"] and s2["lecturerNote"]["text"] == note)
    n = psql(f"select count(*), max(link_to) from notifications where user_id = '{sv_uid}' and link_to like '%{sid}%'")
    cnt, link = n.split("|")
    check("học viên nhận 1 thông báo, link mở đúng buổi", cnt == "1" and f"buoi=SESSION-{sid}" in link and f"ngay={sdate}" in link, n)
    check("ghi chú CSV (`note`) không bị đổi", s2["note"] == s["note"])

    print("\n[4] Không báo khi notify=false; ghi lại cùng nội dung không tạo thông báo")
    gv.req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": note})
    gv.req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": note + " (sửa chính tả)", "notify": False})
    cnt2 = psql(f"select count(*) from notifications where user_id = '{sv_uid}' and link_to like '%{sid}%'")
    check("vẫn chỉ 1 thông báo", cnt2 == "1", cnt2)

    print("\n[5] Ca thi + cán bộ quản lý")
    s_code, r = qldt.req("PUT", f"/schedules/exams/{eid}/lecturer-note", {"note": "Chỉ được mang một tờ A4 viết tay."})
    check("QLĐT ghi yêu cầu ca thi -> 200", s_code == 200 and r["kind"] == "EXAM" and r["lecturerNote"]["updatedBy"], str(r)[:200])
    ex2 = next(x for x in my_week(edate)["exams"] if x["id"] == eid)
    check("học viên thấy yêu cầu ca thi", ex2["lecturerNote"]["text"].startswith("Chỉ được mang"))

    print("\n[6] Lịch giảng dạy")
    s_code, t = gv.req("GET", f"/schedules/teaching?from={sdate}&to={sdate}")
    check("giảng viên: 200, chỉ môn mình phụ trách",
          s_code == 200 and t["sessions"] and all(x["course"]["code"] == "CS301" for x in t["sessions"]) and not t["canEditAll"], str(t)[:200])
    check("mỗi buổi kèm lớp", all(x["class"] and x["class"]["code"] for x in t["sessions"]))
    s_code, t2 = gv2.req("GET", f"/schedules/teaching?from={sdate}&to={sdate}")
    check("giảng viên không phụ trách môn nào: rỗng", s_code == 200 and t2["sessions"] == [] and t2["exams"] == [])
    s_code, t3 = qldt.req("GET", f"/schedules/teaching?from={sdate}&to={sdate}")
    check("QLĐT: thấy mọi môn, canEditAll", s_code == 200 and t3["canEditAll"] and len(t3["sessions"]) >= len(t["sessions"]))
    check("học viên gọi lịch giảng dạy -> 403", sv.req("GET", "/schedules/teaching")[0] == 403)

    print("\n[7] Xóa yêu cầu")
    s_code, r = gv.req("PUT", f"/schedules/sessions/{sid}/lecturer-note", {"note": "   "})
    check("chuỗi trắng = xóa", s_code == 200 and r["lecturerNote"] is None, str(r)[:150])
finally:
    psql(f"update schedules set lecturer_note = null, lecturer_note_updated_at = null, lecturer_note_by_id = null where id = '{sid}'")
    psql(f"update exam_schedules set lecturer_note = null, lecturer_note_updated_at = null, lecturer_note_by_id = null where id = '{eid}'")
    psql(f"delete from notifications where link_to like '%{sid}%' or link_to like '%{eid}%'")

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
