"""Helper HTTP dùng chung cho các bài kiểm thử /learning (không tự chạy gì)."""

from __future__ import annotations

import http.cookiejar
import json
import subprocess
import sys
import urllib.error
import urllib.request

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

# 127.0.0.1 thay vì localhost: trên Windows `localhost` thử IPv6 trước nên mỗi lệnh gọi tốn thêm ~2 giây.
BASE = "http://127.0.0.1:5000/api"
PASSED = FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}  {detail}")


class Client:
    def __init__(self) -> None:
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(
            BASE + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with self.opener.open(r, timeout=180) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except json.JSONDecodeError:
                return e.code, {}


def login(email: str, password: str = "Demo@2026") -> Client:
    # Các bộ test dùng lại cùng tài khoản liên tiếp, nhanh hơn giới hạn theo phút: xóa bộ đếm của email và của chính người dùng này.
    mail = email.strip().lower()
    psql(
        "DELETE FROM rate_limits WHERE (bucket = 'login-email' AND key = '%s') "
        "OR key = (SELECT id::text FROM users WHERE email = '%s')" % (mail, mail)
    )
    c = Client()
    status, _ = c.req("POST", "/auth/login", {"email": email, "password": password})
    if status != 200 and status != 201:
        sys.exit(f"Không đăng nhập được {email}: {status}")
    return c


def psql(sql: str) -> str:
    return subprocess.run(
        ["docker", "exec", "sa-postgres-dev", "psql", "-U", "student_assistant", "-d", "student_assistant_py", "-tAc", sql],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
