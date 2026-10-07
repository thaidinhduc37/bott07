"""Kiểm thử nhập danh sách học viên từ CSV: POST /catalog/students/import.

Dữ liệu thử dùng tiền tố `ZT` / `zt-` và được dọn lại ở cuối (kể cả khi có lỗi).

    python scripts/test/test_student_import.py
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

qldt = login("qldt@hvktcnan.edu.vn")
gv = login("gv.nguyenvanminh@hvktcnan.edu.vn")
sv = login("sv.nguyenducanh@hvktcnan.edu.vn")

HEAD = "ma_hv,ho_ten,email,ma_lop,khoa_hoc,sdt\n"


def cleanup() -> None:
    psql("delete from users where email like 'zt-%@hvktcnan.edu.vn'")
    psql("delete from classes where code like 'ZT%'")


def upload(client, content: str, dry: bool = False, filename: str = "hv.csv") -> tuple[int, dict]:
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n{content}\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/catalog/students/import" + ("?dryRun=true" if dry else ""), data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with client.opener.open(req, timeout=120) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


cleanup()
try:
    psql("insert into classes (id, code, name) values (gen_random_uuid(), 'ZTLOP1', 'Lớp thử nhập')")
    psql("insert into classes (id, code, name) values (gen_random_uuid(), 'ZTLOP2', 'Lớp thử nhập 2')")

    good = HEAD + "ZT0001,Trần Văn A,zt-a@hvktcnan.edu.vn,ZTLOP1,2026,0901234567\nZT0002,Lê Thị B,zt-b@hvktcnan.edu.vn,ZTLOP1,2026,\n"

    # --- quyền
    st, _ = upload(gv, good, dry=True)
    check("giảng viên không nhập được", st == 403, str(st))
    st, _ = upload(sv, good, dry=True)
    check("học viên không nhập được", st == 403, str(st))

    # --- chạy thử không ghi
    st, d = upload(qldt, good, dry=True)
    check("chạy thử hợp lệ", st == 200 and d["dryRun"] and d["created"] == 2 and not d["errors"], f"{st} {str(d)[:300]}")
    check("chạy thử không ghi gì", psql("select count(*) from users where email like 'zt-%@hvktcnan.edu.vn'") == "0")
    check("chạy thử không trả mật khẩu", d["credentials"] == [])

    # --- lỗi từng dòng, không ghi gì
    bad = HEAD + (
        "ZT0003,A,zt-c@hvktcnan.edu.vn,ZTLOP1,,\n"                      # tên quá ngắn
        "ZT0004,Phạm D,khong-phai-email,ZTLOP1,,\n"                     # email sai
        "ZT0005,Hồ E,zt-e@hvktcnan.edu.vn,KHONGCO,,\n"                  # lớp không có
        "ZT0006,Vũ F,zt-f@hvktcnan.edu.vn,,,12345\n"                    # sđt sai
        "ZT0006,Vũ G,zt-g@hvktcnan.edu.vn,,,\n"                         # trùng mã trong tệp
        "ZT0007,Đỗ H,sv.nguyenducanh@hvktcnan.edu.vn,,,\n"              # email đã thuộc người khác
        "B3D15001,Nguyễn Đức Anh,khac@hvktcnan.edu.vn,,,\n"             # mã có sẵn, email khác
    )
    st, d = upload(qldt, bad)
    lines = {e["line"] for e in d.get("errors", [])}
    check("báo đủ 7 dòng lỗi", st == 200 and lines == {2, 3, 4, 5, 6, 7, 8}, f"{st} {sorted(lines)} {str(d)[:300]}")
    check("còn lỗi thì không ghi", d.get("accepted") is False and psql("select count(*) from users where email like 'zt-%@hvktcnan.edu.vn'") == "0")

    # --- tệp sai định dạng
    st, d = upload(qldt, "a,b\n1,2\n")
    check("thiếu cột bắt buộc → 400", st == 400 and d.get("code") == "BAD_HEADER", f"{st} {d}")

    # --- ghi thật
    st, d = upload(qldt, good)
    check("nhập thật tạo 2 tài khoản", st == 200 and d["accepted"] and d["created"] == 2 and len(d["credentials"]) == 2, f"{st} {str(d)[:300]}")
    check("tài khoản có vai trò học viên và vào đúng lớp", psql(
        "select count(*) from users u join user_roles ur on ur.user_id=u.id join roles r on r.id=ur.role_id "
        "join student_profiles p on p.user_id=u.id join classes c on c.id=p.class_id "
        "where u.email like 'zt-%@hvktcnan.edu.vn' and r.code='STUDENT' and c.code='ZTLOP1'") == "2")

    # --- mật khẩu cấp ra đăng nhập được, không lưu dạng rõ
    cred = next(c for c in d["credentials"] if c["studentCode"] == "ZT0001")
    check("mật khẩu đủ mạnh", len(cred["password"]) >= 10)
    try:
        c = login(cred["email"], cred["password"])
        st, me = c.req("GET", "/users/me")
        check("học viên mới đăng nhập được", st == 200 and me.get("studentProfile", {}).get("studentCode") == "ZT0001", f"{st}")
    except Exception as e:  # noqa: BLE001
        check("học viên mới đăng nhập được", False, str(e))
    check("không lưu mật khẩu rõ", cred["password"] not in psql("select password_hash from users where email='zt-a@hvktcnan.edu.vn'"))
    check("nhật ký không chứa mật khẩu", cred["password"] not in psql("select coalesce(string_agg(detail::text, ' '), '') from audit_logs where action='STUDENTS_IMPORT'"))

    # --- chạy lại cùng tệp: không tạo trùng
    st, d = upload(qldt, good)
    check("chạy lại không tạo trùng", st == 200 and d["created"] == 0 and d["unchanged"] == 2 and d["credentials"] == [], f"{st} {str(d)[:300]}")

    # --- cập nhật: đổi lớp và tên, email giữ nguyên
    upd = HEAD + "ZT0001,Trần Văn An,zt-a@hvktcnan.edu.vn,ZTLOP2,2027,\nZT0002,Lê Thị B,zt-b@hvktcnan.edu.vn,,,\n"
    st, d = upload(qldt, upd)
    check("cập nhật 1, giữ nguyên 1", st == 200 and d["created"] == 0 and d["updated"] == 1 and d["unchanged"] == 1, f"{st} {str(d)[:300]}")
    got = psql(
        "select (u.full_name like '%n An')::text || '|' || c.code || '|' || p.cohort from users u join student_profiles p on p.user_id=u.id "
        "join classes c on c.id=p.class_id where u.email='zt-a@hvktcnan.edu.vn'")
    check("tên, lớp, khóa đã đổi", got == "true|ZTLOP2|2027", repr(got))
    check("ô trống không xóa lớp", psql("select c.code from student_profiles p join classes c on c.id=p.class_id join users u on u.id=p.user_id where u.email='zt-b@hvktcnan.edu.vn'") == "ZTLOP1")
finally:
    cleanup()

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
