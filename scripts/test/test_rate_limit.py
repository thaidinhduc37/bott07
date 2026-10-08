"""Kiểm thử giới hạn tần suất: cả trường có thể chung một IP nên đăng nhập tính theo email, thao tác đã đăng nhập tính theo người dùng.

    python scripts/test/test_rate_limit.py
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import Client, check, login, psql  # noqa: E402

anon = Client()
psql("DELETE FROM rate_limits")  # bắt đầu từ bộ đếm trống để chạy lại trong cùng một phút vẫn đúng


def fresh_window() -> None:
    """Bộ đếm theo cửa sổ 60 giây: chờ sang cửa sổ mới nếu sắp hết để một loạt lượt không bị tách đôi."""
    left = 60 - time.time() % 60
    if left < 15:
        time.sleep(left + 0.5)


fresh_window()

# Nhiều email khác nhau từ cùng một IP không bị chặn (trước đây mỗi IP chỉ 5 lần/phút).
codes = [anon.req("POST", "/auth/login", {"email": f"zt-rl-{uuid.uuid4().hex[:8]}@hvktcnan.edu.vn", "password": "sai-mat-khau"})[0] for _ in range(8)]
check("8 email khác nhau cùng IP: không ai bị 429", codes == [401] * 8, str(codes))

# Cùng một email: lần thứ 6 trong một phút bị chặn (chống dò mật khẩu một tài khoản).
victim = f"zt-rl-{uuid.uuid4().hex[:8]}@hvktcnan.edu.vn"
codes = [anon.req("POST", "/auth/login", {"email": victim, "password": "sai-mat-khau"})[0] for _ in range(6)]
check("cùng một email: 5 lần đầu 401, lần thứ 6 bị 429", codes == [401] * 5 + [429], str(codes))
st, body = anon.req("POST", "/auth/login", {"email": victim.upper(), "password": "sai-mat-khau"})
check("email viết hoa vẫn tính chung một bộ đếm", st == 429 and body.get("code") == "RATE_LIMITED", f"{st} {body}")

# Làm mới phiên: mỗi refresh token 20 lần/phút.
fresh_window()
codes = [anon.req("POST", "/auth/refresh")[0] for _ in range(21)]
check("refresh: 20 lần đầu 401 (không có token), lần thứ 21 bị 429", codes[:20] == [401] * 20 and codes[20] == 429, str(codes[-3:]))

# Thao tác đã đăng nhập tính theo người dùng: học viên A hết lượt không ảnh hưởng học viên B.
a = login("sv.nguyenducanh@hvktcnan.edu.vn")
b = login("sv.tranthimai@hvktcnan.edu.vn")
limit = 12
fresh_window()
codes_a = [a.req("POST", "/learning/quiz", {})[0] for _ in range(limit + 1)]
check(f"học viên A: {limit} lần đầu qua giới hạn (400 do thiếu chủ đề), lần kế tiếp bị 429", codes_a[:limit] == [400] * limit and codes_a[limit] == 429, str(codes_a))
st_b, _ = b.req("POST", "/learning/quiz", {})
check("học viên B không bị ảnh hưởng (vẫn 400, không 429)", st_b == 400, str(st_b))

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
