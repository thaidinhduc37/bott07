"""Port of `health/health.controller.ts`.

`/api/health` is public and deliberately terse (just enough for Docker to know
the container is alive). `/api/health/detail` is ADMIN-only and reports RAG
pipeline health.

Originally this called a separate `rag-service` HTTP process. Now that the
pipeline runs in-process (see `app/rag_container.py`,
`app/services/rag_client.py`), this just calls `RagClientService.health()`
directly in Python — no HTTP hop, and "unreachable" is no longer a possible
failure mode (a Chroma outage still shows up via `chroma.ok` inside the
result).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_roles
from app.models.documents import DocumentVersion
from app.models.enums import IndexStatus, RoleCode
from app.models.forms import FormSubmission
from app.models.users import User
from app.services.rag_client import get_rag_client

router = APIRouter(prefix="/health", tags=["health"])

_start_time = time.monotonic()


@router.get("")
async def health(db: AsyncSession = Depends(get_db)):
    ok = False
    try:
        await db.execute(text("SELECT 1"))
        ok = True
    except Exception:
        ok = False
    return {"status": "ok" if ok else "degraded", "service": "api"}


@router.get("/detail", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def health_detail(db: AsyncSession = Depends(get_db)):
    started = time.monotonic()
    db_ok = False
    db_latency_ms: int | None = None
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
        db_latency_ms = round((time.monotonic() - started) * 1000)
    except Exception:
        db_ok = False

    rag_ok = False
    rag_detail = ""
    collections: dict = {}
    llm = None
    try:
        body = (await get_rag_client().health()).model_dump()
        rag_ok = body.get("status") == "ok"
        rag_detail = body.get("status") or "unknown"
        collections = body.get("collections") or {}
        llm = (body.get("dependencies") or {}).get("llm")
    except Exception as e:  # noqa: BLE001
        rag_detail = str(e)

    users_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    submissions_count = (await db.execute(select(func.count()).select_from(FormSubmission))).scalar_one()
    indexed_docs = (
        await db.execute(
            select(func.count()).select_from(DocumentVersion).where(DocumentVersion.index_status == IndexStatus.INDEXED)
        )
    ).scalar_one()
    try:
        import resource

        memory_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    except ImportError:
        # `resource` isn't available on Windows — fall back to psutil-free /proc
        # reading is also unavailable there, so report 0 rather than guessing.
        memory_mb = _windows_rss_mb()

    return {
        "status": "ok" if db_ok and rag_ok else "degraded",
        "dependencies": {
            "postgres": {"ok": db_ok, "latencyMs": db_latency_ms},
            "ragService": {"ok": rag_ok, "detail": rag_detail, "url": "in-process", "collections": collections},
            "llm": llm,
        },
        "counters": {
            "users": users_count,
            "indexedDocumentVersions": indexed_docs,
            "submissions": submissions_count,
        },
        "uptimeSeconds": round(time.monotonic() - _start_time),
        "memoryMb": memory_mb,
    }


def _windows_rss_mb() -> int:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                )
            ]

        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        # Khai báo kiểu HANDLE tường minh: mặc định ctypes coi giá trị trả về là int
        # 32-bit, pseudo-handle -1 trên Windows 64-bit bị cắt và lời gọi thất bại
        # âm thầm — trước đây hàm này vì thế luôn trả 0.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD,
        ]
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return 0
        return round(counters.WorkingSetSize / 1024 / 1024)
    except Exception:
        return 0
