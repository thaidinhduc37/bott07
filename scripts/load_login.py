"""Đo cơn bão đăng nhập: nhiều học viên đăng nhập cùng lúc từ một IP, kèm độ trễ của /health trong lúc đó.

    python scripts/load_login.py --users 120
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import AsyncSessionLocal  # noqa: E402

BASE = "http://127.0.0.1:5000/api"
PASSWORD = "Demo@2026"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        emails = (
            await db.execute(
                text("SELECT u.email FROM users u JOIN student_profiles p ON p.user_id = u.id "
                     "WHERE p.student_code LIKE 'DM%' ORDER BY random() LIMIT :n"),
                {"n": args.users},
            )
        ).scalars().all()

    login_ms: list[float] = []
    health_ms: list[float] = []
    failures: dict[int | str, int] = {}
    done = asyncio.Event()

    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=args.users + 10)) as client:

        async def login(email: str) -> None:
            started = time.perf_counter()
            try:
                code = (await client.post(f"{args.base}/auth/login", json={"email": email, "password": PASSWORD}, timeout=30)).status_code
            except httpx.HTTPError as exc:
                code = type(exc).__name__
            login_ms.append((time.perf_counter() - started) * 1000)
            if code != 200:
                failures[code] = failures.get(code, 0) + 1

        async def ping() -> None:
            while not done.is_set():
                started = time.perf_counter()
                try:
                    await client.get(f"{args.base}/health", timeout=20)
                except httpx.HTTPError as exc:
                    failures["health:" + type(exc).__name__] = failures.get("health:" + type(exc).__name__, 0) + 1
                health_ms.append((time.perf_counter() - started) * 1000)
                await asyncio.sleep(0.05)

        pinger = asyncio.create_task(ping())
        started = time.perf_counter()
        await asyncio.gather(*(login(e) for e in emails))
        elapsed = time.perf_counter() - started
        done.set()
        await pinger

    def pct(values: list[float], p: int) -> float:
        return statistics.quantiles(values, n=100)[p - 1] if len(values) > 1 else values[0]

    print(f"{len(emails)} lượt đăng nhập đồng thời trong {elapsed:.1f}s = {len(emails) / elapsed:.1f} lượt/giây")
    print(f"đăng nhập   p50 {pct(login_ms, 50):.0f}ms  p95 {pct(login_ms, 95):.0f}ms  max {max(login_ms):.0f}ms")
    print(f"/health     p50 {pct(health_ms, 50):.0f}ms  p95 {pct(health_ms, 95):.0f}ms  max {max(health_ms):.0f}ms  ({len(health_ms)} lần đo)")
    print("lỗi:", failures or "không")


if __name__ == "__main__":
    asyncio.run(main())
