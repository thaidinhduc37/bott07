"""Các dependency dùng chung của FastAPI: phiên DB, người dùng hiện tại, kiểm vai trò, giới hạn tần suất.

Mọi route không công khai phải khai báo `Depends(get_current_user)` hoặc `require_roles(...)` (đã gồm cái trước); route công
khai (đăng nhập, refresh, health) thì không. `get_db` được re-export từ `app.core.db`.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.core import rate_limit as rate_limit_store
from app.core.db import get_db  # noqa: F401  (re-exported)
from app.core.security import TokenExpiredError, TokenInvalidError, client_ip, decode_access_token


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
    except TokenExpiredError as exc:
        raise _unauthenticated("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn") from exc
    except TokenInvalidError as exc:
        raise _unauthenticated("UNAUTHENTICATED", "Bạn cần đăng nhập để thực hiện thao tác này") from exc

    user = AuthenticatedUser(
        id=payload["sub"],
        email=payload["email"],
        full_name=payload["name"],
        roles=payload.get("roles", []),
    )
    request.state.user = user
    return user


def require_roles(*roles: str):
    """Người dùng phải có ÍT NHẤT MỘT trong các vai trò đã cho. Chỉ đọc vai trò trong JWT, không truy vấn lại CSDL: vai trò đổi
    có hiệu lực chậm nhất sau 15 phút."""

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

check_rate_limit = rate_limit_store.check


def rate_limit(bucket: str, limit: int):
    """Dependency: tối đa `limit` yêu cầu mỗi 60 giây cho mỗi (bucket, IP). Chỉ dùng cho route chưa đăng nhập."""

    async def _dep(request: Request) -> None:
        await rate_limit_store.check(bucket, client_ip(request), limit)

    return _dep


def user_rate_limit(bucket: str, limit: int):
    """Dependency: tối đa `limit` yêu cầu mỗi 60 giây cho mỗi người dùng đã đăng nhập, không theo IP (cả trường có thể chung một IP)."""

    async def _dep(user: AuthenticatedUser = Depends(get_current_user)) -> None:
        await rate_limit_store.check(bucket, user.id, limit)

    return _dep
