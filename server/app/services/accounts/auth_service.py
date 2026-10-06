"""Port of `auth/auth.service.ts`.

Preserves: dummy-hash timing mitigation on login, Argon2id everywhere,
refresh-token rotation + reuse detection (revoke-all on reuse), revoke-all on
password change / non-ACTIVE status, PIN verification with the same timing
mitigation as login.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.models.enums import UserStatus
from app.models.users import RefreshToken, User, UserRole
from app.core.security import (
    client_ip,
    create_access_token,
    dummy_hash,
    hash_password,
    hash_token,
    new_refresh_token,
    refresh_ttl_seconds,
    verify_password,
)
from app.services.accounts.audit_service import AuditService


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


@dataclass
class AuthenticatedUser:
    id: str
    email: str
    full_name: str
    roles: list[str]


@dataclass
class LoginResult:
    tokens: TokenPair
    user: AuthenticatedUser
    must_set_signature_pin: bool


def _api_error(status_code: int, message: str, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"message": message, "code": code})


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def _get_user_with_roles(self, *, email: str | None = None, user_id: str | None = None) -> User | None:
        stmt = select(User).options(selectinload(User.roles).selectinload(UserRole.role))
        if email is not None:
            stmt = stmt.where(User.email == email)
        else:
            stmt = stmt.where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def login(self, email: str, password: str, request: Request) -> LoginResult:
        user = await self._get_user_with_roles(email=email)

        hash_to_verify = user.password_hash if user else dummy_hash()
        password_ok = verify_password(hash_to_verify, password)

        if not user or not password_ok:
            await self.audit.log(
                action="LOGIN_FAILED",
                user_id=str(user.id) if user else None,
                entity_type="User",
                entity_id=str(user.id) if user else None,
                detail={"email": email, "reason": "WRONG_PASSWORD" if user else "UNKNOWN_EMAIL"},
                request=request,
            )
            await self.db.commit()
            raise _api_error(
                status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng", "INVALID_CREDENTIALS"
            )

        if user.status != UserStatus.ACTIVE:
            await self.audit.log(
                action="LOGIN_BLOCKED",
                user_id=str(user.id),
                entity_type="User",
                entity_id=str(user.id),
                detail={"status": user.status.value},
                request=request,
            )
            await self.db.commit()
            message = (
                "Tài khoản đang bị tạm khóa. Liên hệ quản trị viên."
                if user.status == UserStatus.SUSPENDED
                else "Tài khoản đã bị vô hiệu hóa."
            )
            raise _api_error(status.HTTP_401_UNAUTHORIZED, message, "ACCOUNT_NOT_ACTIVE")

        roles = [ur.role.code.value for ur in user.roles]
        tokens = await self._issue_tokens(user_id=str(user.id), email=user.email, full_name=user.full_name,
                                           roles=roles, request=request)

        user.last_login_at = datetime.now(timezone.utc)
        await self.audit.log(
            action="LOGIN",
            user_id=str(user.id),
            entity_type="User",
            entity_id=str(user.id),
            detail={"roles": roles},
            request=request,
        )
        await self.db.commit()

        return LoginResult(
            tokens=tokens,
            user=AuthenticatedUser(id=str(user.id), email=user.email, full_name=user.full_name, roles=roles),
            must_set_signature_pin=not user.signature_pin_hash,
        )

    async def _issue_tokens(
        self, *, user_id: str, email: str, full_name: str, roles: list[str], request: Request
    ) -> TokenPair:
        access_token, access_seconds = create_access_token(sub=user_id, email=email, name=full_name, roles=roles)

        raw_refresh = new_refresh_token()
        refresh_seconds = refresh_ttl_seconds()

        ua = request.headers.get("user-agent")
        self.db.add(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_token(raw_refresh),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=refresh_seconds),
                user_agent=ua[:500] if ua else None,
                ip_address=client_ip(request),
            )
        )
        await self.db.flush()

        return TokenPair(
            access_token=access_token,
            refresh_token=raw_refresh,
            access_expires_in=access_seconds,
            refresh_expires_in=refresh_seconds,
        )

    async def refresh(self, raw_token: str, request: Request) -> TokenPair:
        if not raw_token:
            raise _api_error(status.HTTP_401_UNAUTHORIZED, "Thiếu refresh token", "NO_REFRESH_TOKEN")

        token_hash = hash_token(raw_token)
        result = await self.db.execute(
            select(RefreshToken)
            .options(selectinload(RefreshToken.user).selectinload(User.roles).selectinload(UserRole.role))
            .where(RefreshToken.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()

        if not record:
            raise _api_error(status.HTTP_401_UNAUTHORIZED, "Refresh token không hợp lệ", "INVALID_REFRESH_TOKEN")

        if record.revoked_at is not None:
            await self.db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == record.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await self.audit.log(
                action="REFRESH_TOKEN_REUSE",
                user_id=str(record.user_id),
                entity_type="RefreshToken",
                entity_id=str(record.id),
                request=request,
            )
            await self.db.commit()
            raise _api_error(
                status.HTTP_401_UNAUTHORIZED,
                "Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.",
                "REFRESH_TOKEN_REUSED",
            )

        now = datetime.now(timezone.utc)
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            raise _api_error(status.HTTP_401_UNAUTHORIZED, "Refresh token đã hết hạn", "REFRESH_TOKEN_EXPIRED")

        if record.user.status != UserStatus.ACTIVE:
            raise _api_error(status.HTTP_401_UNAUTHORIZED, "Tài khoản không còn hoạt động", "ACCOUNT_NOT_ACTIVE")

        record.revoked_at = now
        await self.db.flush()

        roles = [ur.role.code.value for ur in record.user.roles]
        tokens = await self._issue_tokens(
            user_id=str(record.user.id),
            email=record.user.email,
            full_name=record.user.full_name,
            roles=roles,
            request=request,
        )
        await self.db.commit()
        return tokens

    async def logout(self, raw_token: str | None, user_id: str | None, request: Request) -> None:
        if raw_token:
            await self.db.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(timezone.utc))
            )
        if user_id:
            await self.audit.log(action="LOGOUT", user_id=user_id, entity_type="User", entity_id=user_id, request=request)
        await self.db.commit()

    async def revoke_all_sessions(self, user_id: str) -> int:
        result = await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        return result.rowcount or 0

    async def change_password(self, user_id: str, current: str, next_: str, request: Request) -> None:
        user = await self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})

        ok = verify_password(user.password_hash, current)
        if not ok:
            await self.audit.log(
                action="PASSWORD_CHANGE_FAILED", user_id=user_id, entity_type="User", entity_id=user_id,
                request=request,
            )
            await self.db.commit()
            raise HTTPException(
                status_code=400, detail={"message": "Mật khẩu hiện tại không đúng", "code": "WRONG_PASSWORD"}
            )
        if current == next_:
            raise HTTPException(status_code=400, detail={"message": "Mật khẩu mới phải khác mật khẩu hiện tại"})

        user.password_hash = hash_password(next_)
        revoked = await self.revoke_all_sessions(user_id)

        await self.audit.log(
            action="PASSWORD_CHANGED",
            user_id=user_id,
            entity_type="User",
            entity_id=user_id,
            detail={"revokedSessions": revoked},
            request=request,
        )
        await self.db.commit()

    async def set_signature_pin(self, user_id: str, password: str, pin: str, request: Request) -> None:
        user = await self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})
        ok = verify_password(user.password_hash, password)
        if not ok:
            raise HTTPException(status_code=400, detail={"message": "Mật khẩu không đúng", "code": "WRONG_PASSWORD"})

        user.signature_pin_hash = hash_password(pin)
        await self.audit.log(
            action="SIGNATURE_PIN_SET", user_id=user_id, entity_type="User", entity_id=user_id, request=request
        )
        await self.db.commit()

    async def verify_signature_pin(self, user_id: str, pin: str) -> bool:
        user = await self.db.get(User, user_id)
        hash_ = user.signature_pin_hash if user and user.signature_pin_hash else dummy_hash()
        ok = verify_password(hash_, pin)
        return bool(user and user.signature_pin_hash) and ok
