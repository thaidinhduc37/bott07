"""Insert-only audit log service. Port of `audit/audit.service.ts`.

Two rules, preserved exactly:

1. Logging must never break business logic. If the INSERT into `audit_logs`
   fails, log the failure and move on — never raise. An approved form rolling
   back because the audit insert failed is worse than losing one log line.
2. Never copy a whole row into `detail` — only the fields that actually
   changed, via `diff()`. Copying whole rows both bloats the table and risks
   leaking something like `password_hash` into a table admins can read.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models.audit import AuditLog
from app.core.security import client_ip

logger = logging.getLogger("audit")


def _to_json(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        *,
        action: str,
        user_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        detail: dict | None = None,
        request: Request | None = None,
    ) -> None:
        try:
            user_agent = None
            ip = None
            if request is not None:
                ip = client_ip(request)
                ua = request.headers.get("user-agent")
                user_agent = ua[:500] if ua else None
            # Flush inside a SAVEPOINT (nested transaction): if the insert
            # fails (e.g. an unexpected FK/constraint issue), only this
            # savepoint rolls back — the caller's outer transaction and any
            # writes already pending in it stay intact and can still commit.
            # Flushing directly on the outer transaction would instead poison
            # the whole transaction on failure, which is exactly the "audit
            # insert failure rolls back an approved form" bug this class
            # exists to avoid.
            async with self.db.begin_nested():
                self.db.add(
                    AuditLog(
                        user_id=user_id,
                        action=action,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        detail=detail,
                        ip_address=ip,
                        user_agent=user_agent,
                    )
                )
                await self.db.flush()
        except Exception as e:  # noqa: BLE001 - audit logging must never raise
            logger.error(f'Could not write audit log for "{action}": {e}')

    @staticmethod
    def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        """Field-by-field comparison; returns only fields that actually changed."""
        changes: dict[str, Any] = {}
        for key, next_val in after.items():
            if next_val is None and key not in before:
                continue
            prev = before.get(key)
            same = prev == next_val
            if isinstance(prev, datetime) and isinstance(next_val, datetime):
                same = prev == next_val
            if not same:
                changes[key] = {"from": _to_json(prev), "to": _to_json(next_val)}
        return changes
