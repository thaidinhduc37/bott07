"""Shared FastAPI dependencies: DB session, current user, role guard, rate limit.

Port of the JwtAuthGuard / RolesGuard / ThrottlerGuard trio + `@CurrentUser()`.
`get_db` is re-exported from `app.core.db` so every router can `from app.core.deps import
get_db, get_current_user, require_roles`.

Fail-closed: `get_current_user` is meant to be a dependency on EVERY route by
default. Routes that must be public (login, refresh, health) simply don't
depend on it — there is no global-guard-plus-opt-out mechanism in FastAPI the
way there is in Nest, so "public by omission" is the equivalent here: every
router in this codebase must explicitly add `Depends(get_current_user)` (or a
`require_roles(...)` dependency, which implies it) to every non-public route.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.db import get_db  # noqa: F401  (re-exported)
from app.core.security import TokenExpiredError, TokenInvalidError, decode_access_token


@dataclass
class AuthenticatedUser:
    id: str
    email: str
    full_name: str
    roles: list[str]


def _unauthenticated(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"message": message, "code": code})


async def get_current_user(
    request: Request,
    sa_access: str | None = Cookie(default=None),
) -> AuthenticatedUser:
    token = sa_access
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
    if not token:
        raise _unauthenticated("UNAUTHENTICATED", "Bạn cần đăng nhập để thực hiện thao tác này")

    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise _unauthenticated("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn")
    except TokenInvalidError:
        raise _unauthenticated("UNAUTHENTICATED", "Bạn cần đăng nhập để thực hiện thao tác này")

    user = AuthenticatedUser(
        id=payload["sub"],
        email=payload["email"],
        full_name=payload["name"],
        roles=payload.get("roles", []),
    )
    request.state.user = user
    return user


def require_roles(*roles: str):
    """Dependency factory: user must have AT LEAST ONE of the given roles.

    Role check reads JWT claims only (not re-queried from DB) — same 15-minute
    staleness tradeoff as the NestJS RolesGuard.
    """

    async def _dep(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not any(r in user.roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Bạn không có quyền thực hiện thao tác này",
                    "code": "FORBIDDEN",
                    "requiredRoles": list(roles),
                },
            )
        return user

    return _dep


# --------------------------------------------------------------- rate limit

class _InMemoryRateLimiter:
    """Small fixed-window in-memory limiter — single-process only, matches the
    scope of a Phase 1 smoke-testable server. Good enough for `uvicorn` running
    as one worker; a multi-worker/production deployment would need a shared
    store (Redis) instead, same caveat `slowapi`'s default backend has.
    """

    def __init__(self):
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(list)

    def check(self, bucket: str, key: str, limit: int, window_seconds: float = 60.0) -> None:
        now = time.monotonic()
        hits = self._hits[(bucket, key)]
        cutoff = now - window_seconds
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"message": "Quá nhiều yêu cầu, vui lòng thử lại sau", "code": "RATE_LIMITED"},
            )
        hits.append(now)


_limiter = _InMemoryRateLimiter()


def rate_limit(bucket: str, limit: int):
    """Dependency factory: `limit` requests per 60s per (bucket, client IP)."""

    def _dep(request: Request) -> None:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )
        _limiter.check(bucket, ip, limit)

    return _dep


def default_rate_limit():
    s = get_settings()
    return rate_limit("default", s.rate_limit_default_per_min)
