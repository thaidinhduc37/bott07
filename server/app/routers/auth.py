"""Port of `auth/auth.controller.ts`. Routes mounted at `/api/auth/*`."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import AuthenticatedUser, get_current_user, get_db, rate_limit
from app.models.users import StudentProfile, User, UserRole
from app.schemas.auth import (
    AuthenticatedUserOut,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RefreshResponse,
    SetSignaturePinRequest,
)
from app.core.security import clear_auth_cookies, set_auth_cookies
from app.services.accounts.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(rate_limit("login", 5))])
async def login(dto: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    result = await AuthService(db).login(dto.email, dto.password, request)
    set_auth_cookies(
        response,
        access_token=result.tokens.access_token,
        access_expires_in=result.tokens.access_expires_in,
        refresh_token=result.tokens.refresh_token,
        refresh_expires_in=result.tokens.refresh_expires_in,
    )
    return LoginResponse(
        user=AuthenticatedUserOut(
            id=result.user.id,
            email=result.user.email,
            full_name=result.user.full_name,
            roles=result.user.roles,
            must_set_signature_pin=result.must_set_signature_pin,
        ),
        access_token=result.tokens.access_token,
        expires_in=result.tokens.access_expires_in,
    )


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(rate_limit("refresh", 20))])
async def refresh(
    request: Request,
    response: Response,
    sa_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    try:
        tokens = await AuthService(db).refresh(sa_refresh or "", request)
    except HTTPException:
        clear_auth_cookies(response)
        raise
    set_auth_cookies(
        response,
        access_token=tokens.access_token,
        access_expires_in=tokens.access_expires_in,
        refresh_token=tokens.refresh_token,
        refresh_expires_in=tokens.refresh_expires_in,
    )
    return RefreshResponse(access_token=tokens.access_token, expires_in=tokens.access_expires_in)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    sa_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    # Public in Nest too: logout should succeed even with an expired/absent
    # access token, so this route does NOT depend on get_current_user. We
    # still try to attribute the audit entry to a user if the access cookie
    # happens to be valid, matching `req.user?.id` in the Nest controller.
    user_id: str | None = None
    try:
        user = await get_current_user(request, sa_access=request.cookies.get("sa_access"))
        user_id = user.id
    except HTTPException:
        user_id = None

    await AuthService(db).logout(sa_refresh, user_id, request)
    clear_auth_cookies(response)
    return MessageResponse(message="Đã đăng xuất")


@router.get("/me")
async def me(user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(UserRole.role),
            selectinload(User.student_profile).selectinload(StudentProfile.study_class),
        )
        .where(User.id == user.id)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})

    sp = row.student_profile
    return {
        "id": str(row.id),
        "email": row.email,
        "fullName": row.full_name,
        "phone": row.phone,
        "status": row.status,
        "lastLoginAt": row.last_login_at,
        "roles": [ur.role.code for ur in row.roles],
        "roleNames": [ur.role.name for ur in row.roles],
        "hasSignaturePin": bool(row.signature_pin_hash),
        "studentProfile": (
            {
                "studentCode": sp.student_code,
                "cohort": sp.cohort,
                "trainingSystem": sp.training_system,
                "dateOfBirth": sp.date_of_birth,
                "studyClass": (
                    {"id": str(sp.study_class.id), "code": sp.study_class.code, "name": sp.study_class.name}
                    if sp.study_class
                    else None
                ),
            }
            if sp
            else None
        ),
    }


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    dto: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).change_password(user.id, dto.current_password, dto.new_password, request)
    clear_auth_cookies(response)
    return MessageResponse(message="Đổi mật khẩu thành công. Vui lòng đăng nhập lại.")


@router.post(
    "/signature-pin", response_model=MessageResponse, dependencies=[Depends(rate_limit("signature-pin", 5))]
)
async def set_signature_pin(
    dto: SetSignaturePinRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).set_signature_pin(user.id, dto.password, dto.pin, request)
    return MessageResponse(message="Đã cập nhật mã PIN ký")
