"""Đo tải: nhiều học viên và giảng viên dùng đồng thời, báo p50/p95/p99 và số lỗi theo từng endpoint.

Token được ký trực tiếp bằng khóa JWT trong `server/.env` (không đi qua đăng nhập, vốn bị giới hạn tần suất), nên chỉ chạy
với máy chủ và CSDL dev của bạn. Cần dữ liệu demo: `python scripts/seed_demo_scale.py --apply`.

    python scripts/load_test.py                              # 200 học viên + 30 giảng viên đồng thời, 15 lượt mỗi người
    python scripts/load_test.py --students 400 --lecturers 60 --rounds 20
    python scripts/load_test.py --students 1500 --lecturers 100 --rounds 12 --think 8   # người dùng thật: nghỉ ~8 giây giữa các thao tác
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:5000/api"

STUDENT_PATHS = [
    "/users/me",
    "/schedules/me/terms",
    "/schedules/me/enrollments",
    "/schedules/me/exam-term",
    "/schedules/me?from=2026-10-05&to=2026-10-11",
    "/grades/me",
    "/learning/progress",
    "/learning/exam-plan",
    "/learning/review-items",
    "/notifications",
    "/chat/conversations",
]
LECTURER_PATHS = [
    "/users/me",
    "/teaching/classes",
    "/grades/sections",
    "/schedules/teaching?from=2026-10-05&to=2026-10-11",
    "/learning/insights/courses",
    "/question-bank/courses",
    "/notifications",
]


USERS_SQL = """
    SELECT u.id::text, u.email, u.full_name, array_agg(r.code::text) AS roles
    FROM users u JOIN user_roles ur ON ur.user_id = u.id JOIN roles r ON r.id = ur.role_id
    WHERE {where}
    GROUP BY u.id ORDER BY random() LIMIT :n
"""
DEMO_STUDENTS = "EXISTS (SELECT 1 FROM student_profiles p WHERE p.user_id = u.id AND p.student_code LIKE 'DM%')"
DEMO_LECTURERS = "u.faculty_id IN (SELECT id FROM faculties WHERE code LIKE 'DM-%') AND r.code::text = 'LECTURER'"


async def pick_users(students: int, lecturers: int) -> list[tuple[str, dict]]:
    users: list[tuple[str, dict]] = []
    async with AsyncSessionLocal() as db:
        for kind, where, n in (("student", DEMO_STUDENTS, students), ("lecturer", DEMO_LECTURERS, lecturers)):
            for user_id, email, name, roles in (await db.execute(text(USERS_SQL.format(where=where)), {"n": n})).all():
                token, _ = create_access_token(sub=user_id, email=email, name=name, roles=list(roles))
                users.append((kind, {"token": token}))
    return users


async def run_user(
    client: httpx.AsyncClient, base: str, kind: str, token: str, rounds: int, think: float, stats: dict, errors: dict
) -> None:
    paths = STUDENT_PATHS if kind == "student" else LECTURER_PATHS
    cookies = {"sa_access": token}
    await asyncio.sleep(random.uniform(0, think))
    for _ in range(rounds):
        path = random.choice(paths)
        started = time.perf_counter()
        try:
            res = await client.get(base + path, cookies=cookies, timeout=60)
            code = res.status_code
        except httpx.HTTPError as exc:
            code = type(exc).__name__
        stats[(kind, path.split("?")[0])].append((time.perf_counter() - started) * 1000)
        if code != 200:
            errors[(kind, path.split("?")[0], code)] += 1
        if think:
            await asyncio.sleep(random.uniform(0.5, 1.5) * think)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=200)
    ap.add_argument("--lecturers", type=int, default=30)
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--think", type=float, default=0.0, help="Giây nghỉ trung bình giữa hai thao tác của một người (0 = dồn dập).")
    args = ap.parse_args()

    users = await pick_users(args.students, args.lecturers)
    n_students = sum(1 for k, _ in users if k == "student")
    print(f"{n_students} học viên + {len(users) - n_students} giảng viên đồng thời, {args.rounds} lượt mỗi người")
    if not users:
        sys.exit("Không có tài khoản demo — chạy scripts/seed_demo_scale.py --apply trước.")

    stats: dict = defaultdict(list)
    errors: dict = defaultdict(int)
    limits = httpx.Limits(max_connections=len(users) + 10, max_keepalive_connections=len(users))
    started = time.perf_counter()
    async with httpx.AsyncClient(limits=limits) as client:
        await asyncio.gather(*(run_user(client, args.base, k, u["token"], args.rounds, args.think, stats, errors) for k, u in users))
    elapsed = time.perf_counter() - started

    total = sum(len(v) for v in stats.values())
    print(f"\n{total} yêu cầu trong {elapsed:.1f}s = {total / elapsed:.0f} yêu cầu/giây\n")
    print(f"{'endpoint':42} {'n':>5} {'p50':>7} {'p95':>7} {'p99':>7} {'max':>7}  (ms)")
    worst = []
    for (kind, path), vals in sorted(stats.items(), key=lambda kv: -statistics.quantiles(kv[1], n=20)[18] if len(kv[1]) > 1 else 0):
        q = statistics.quantiles(vals, n=100) if len(vals) > 1 else [vals[0]] * 99
        print(f"{kind[0]}:{path:40} {len(vals):5d} {q[49]:7.0f} {q[94]:7.0f} {q[98]:7.0f} {max(vals):7.0f}")
        worst.append(q[94])
    if errors:
        print("\nLỗi:")
        for (kind, path, code), n in sorted(errors.items(), key=lambda kv: -kv[1]):
            print(f"  {n:5d} × {kind[0]}:{path} → {code}")
    else:
        print("\nKhông có lỗi.")


if __name__ == "__main__":
    asyncio.run(main())
