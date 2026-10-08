"""Băm mật khẩu và PIN, JWT, refresh token, cookie.

- Argon2id cho mật khẩu và PIN ký, tham số chi phí lấy từ env.
- Luôn kiểm một băm Argon2id giả (tạo một lần lúc import) khi email không tồn tại, để "sai email" và "sai mật khẩu" tốn
  cùng thời gian.
- Refresh token là chuỗi `secrets.token_urlsafe`; chỉ băm SHA-256 của nó được lưu, token thô chỉ nằm trong cookie.
- Cookie `sa_access` / `sa_refresh`, `sa_refresh` giới hạn ở `/api/auth`.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import Response

from app.core.config import get_settings

ACCESS_COOKIE = "sa_access"
REFRESH_COOKIE = "sa_refresh"
REFRESH_COOKIE_PATH = "/api/auth"

JWT_ALGORITHM = "HS256"


def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.password_hash_iterations,
        memory_cost=s.password_hash_memory_kib,
        parallelism=s.password_hash_parallelism,
    )


def hash_password(plain: str) -> str:
    return _hasher().hash(plain)


def verify_password(hash_: str, plain: str) -> bool:
    try:
        return _hasher().verify(hash_, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:
        return False


# A fresh PasswordHasher() (default cost params) is fine for the dummy hash —
# it only exists to burn roughly the same wall-clock time as a real verify.
_DUMMY_HASH: str = PasswordHasher().hash(secrets.token_hex(32))


def dummy_hash() -> str:
    return _DUMMY_HASH


# ------------------------------------------------------------------- tokens

_TTL_RE = re.compile(r"^(\d+)([smhd])$")
_TTL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_ttl_seconds(value: str, fallback: int) -> int:
    m = _TTL_RE.match(value.strip())
    if not m:
        return fallback
    return int(m.group(1)) * _TTL_UNITS[m.group(2)]


def create_access_token(*, sub: str, email: str, name: str, roles: list[str]) -> tuple[str, int]:
    s = get_settings()
    seconds = parse_ttl_seconds(s.jwt_access_ttl, 900)
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "name": name,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(seconds=seconds),
    }
    token = jwt.encode(payload, s.jwt_access_secret, algorithm=JWT_ALGORITHM)
    return token, seconds


class TokenExpiredError(Exception):
    pass


class TokenInvalidError(Exception):
    pass


def decode_access_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_access_secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError() from e
    except jwt.InvalidTokenError as e:
        raise TokenInvalidError() from e


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_ttl_seconds() -> int:
    s = get_settings()
    return parse_ttl_seconds(s.jwt_refresh_ttl, 7 * 86400)


def safe_equal(a: str, b: str) -> bool:
    """Constant-time string compare."""
    return compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ------------------------------------------------------------------- cookies

def _cookie_kwargs(max_age_seconds: int, path: str = "/") -> dict[str, Any]:
    s = get_settings()
    is_prod = s.node_env == "production"
    return {
        "httponly": True,
        "secure": is_prod,
        "samesite": "lax",
        "path": path,
        "max_age": max_age_seconds,
    }


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    access_expires_in: int,
    refresh_token: str,
    refresh_expires_in: int,
) -> None:
    response.set_cookie(ACCESS_COOKIE, access_token, **_cookie_kwargs(access_expires_in))
    response.set_cookie(
        REFRESH_COOKIE, refresh_token, **_cookie_kwargs(refresh_expires_in, REFRESH_COOKIE_PATH)
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def client_ip(request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
