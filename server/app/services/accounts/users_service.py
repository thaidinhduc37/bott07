"""Tài khoản người dùng: hồ sơ cá nhân, quản trị tài khoản và vai trò, nhật ký thao tác."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.models.academic import Faculty, StudyClass
from app.models.audit import AuditLog
from app.models.enums import RoleCode, UserStatus
from app.models.users import Role, StudentProfile, User, UserRole
from app.schemas.users import (
    CreateUserRequest,
    UpdateMyProfileRequest,
    UpdateUserRolesRequest,
    UpdateUserStatusRequest,
)
from app.core.security import hash_password
from app.services.accounts.audit_service import AuditService


class UsersService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # --------------------------------------------------------- self-service

    async def get_my_profile(self, user_id: str) -> dict:
        stmt = (
            select(User)
            .options(
                selectinload(User.roles).selectinload(UserRole.role),
                selectinload(User.student_profile).selectinload(StudentProfile.study_class),
                selectinload(User.signatures),
            )
            .where(User.id == user_id)
        )
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})

        active_signatures = [s for s in user.signatures if s.is_active]
        sp = user.student_profile
        student_profile_out = None
        if sp is not None:
            student_profile_out = {
                "studentCode": sp.student_code,
                "dateOfBirth": sp.date_of_birth,
                "placeOfBirth": sp.place_of_birth,
                "gender": sp.gender,
                "address": sp.address,
                "cohort": sp.cohort,
                "trainingSystem": sp.training_system,
                "enrollYear": sp.enroll_year,
                "studyClass": (
                    {
                        "id": str(sp.study_class.id),
                        "code": sp.study_class.code,
                        "name": sp.study_class.name,
                        "faculty": sp.study_class.faculty,
                    }
                    if sp.study_class
                    else None
                ),
            }

        return {
            "id": str(user.id),
            "email": user.email,
            "fullName": user.full_name,
            "phone": user.phone,
            "status": user.status,
            "lastLoginAt": user.last_login_at,
            "createdAt": user.created_at,
            "roles": [ur.role.code for ur in user.roles],
            "roleNames": [ur.role.name for ur in user.roles],
            "hasSignaturePin": bool(user.signature_pin_hash),
            "hasSignature": len(active_signatures) > 0,
            "studentProfile": student_profile_out,
        }

    async def update_my_profile(self, user_id: str, dto: UpdateMyProfileRequest, request: Request) -> dict:
        stmt = select(User).options(selectinload(User.student_profile)).where(User.id == user_id)
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})

        payload = dto.model_dump(exclude_unset=True)
        user_changes = AuditService.diff({"phone": user.phone}, {"phone": payload.get("phone", user.phone)}) \
            if "phone" in payload else {}
        profile_changes = {}
        if user.student_profile:
            before = {"address": user.student_profile.address, "placeOfBirth": user.student_profile.place_of_birth}
            after = {
                "address": payload.get("address", user.student_profile.address),
                "placeOfBirth": payload.get("placeOfBirth", user.student_profile.place_of_birth),
            }
            if "address" in payload or "placeOfBirth" in payload:
                profile_changes = AuditService.diff(before, after)

        if not user_changes and not profile_changes:
            return await self.get_my_profile(user_id)

        if "phone" in payload:
            user.phone = payload["phone"]
        if user.student_profile and ("address" in payload or "placeOfBirth" in payload):
            if "address" in payload:
                user.student_profile.address = payload["address"]
            if "placeOfBirth" in payload:
                user.student_profile.place_of_birth = payload["placeOfBirth"]

        await self.audit.log(
            action="PROFILE_UPDATE",
            user_id=user_id,
            entity_type="User",
            entity_id=user_id,
            detail={**user_changes, **profile_changes},
            request=request,
        )
        await self.db.commit()
        return await self.get_my_profile(user_id)

    # --------------------------------------------------------------- admin

    async def list_users(self, *, search: str | None, role: RoleCode | None, status_: UserStatus | None,
                          page: int, page_size: int) -> dict:
        stmt = select(User).options(
            selectinload(User.roles).selectinload(UserRole.role),
            selectinload(User.student_profile).selectinload(StudentProfile.study_class),
        )
        count_stmt = select(func.count()).select_from(User)

        conditions = []
        if status_ is not None:
            conditions.append(User.status == status_)
        if role is not None:
            stmt = stmt.join(User.roles).join(UserRole.role)
            count_stmt = count_stmt.join(User.roles).join(UserRole.role)
            conditions.append(Role.code == role)
        if search:
            like = f"%{search}%"
            stmt = stmt.outerjoin(User.student_profile)
            count_stmt = count_stmt.outerjoin(User.student_profile)
            conditions.append(
                or_(
                    User.email.ilike(like),
                    User.full_name.ilike(like),
                    StudentProfile.student_code.ilike(like),
                )
            )

        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = (await self.db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(User.created_at.asc()).offset((page - 1) * page_size).limit(page_size).distinct()
        rows = (await self.db.execute(stmt)).unique().scalars().all()

        items = []
        for u in rows:
            items.append(
                {
                    "id": str(u.id),
                    "email": u.email,
                    "fullName": u.full_name,
                    "phone": u.phone,
                    "status": u.status,
                    "lastLoginAt": u.last_login_at,
                    "createdAt": u.created_at,
                    "roles": [ur.role.code for ur in u.roles],
                    "studentCode": u.student_profile.student_code if u.student_profile else None,
                    "classCode": (
                        u.student_profile.study_class.code
                        if u.student_profile and u.student_profile.study_class
                        else None
                    ),
                }
            )
        # Tổng quan của CẢ hệ thống (không theo bộ lọc / trang): trang quản trị không tự đếm từ 20 dòng đang hiện.
        by_status = (await self.db.execute(select(User.status, func.count()).group_by(User.status))).all()
        by_role = (
            await self.db.execute(
                select(Role.code, func.count()).select_from(UserRole).join(Role, Role.id == UserRole.role_id).group_by(Role.code)
            )
        ).all()
        summary = {
            "status": {getattr(k, "value", k): n for k, n in by_status},
            "roles": {getattr(k, "value", k): n for k, n in by_role},
        }
        return {"total": total, "page": page, "pageSize": page_size, "items": items, "summary": summary}

    async def create_user(self, dto: CreateUserRequest, actor_id: str, request: Request) -> dict:
        existing = (await self.db.execute(select(User).where(User.email == dto.email))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail={"message": f"Email {dto.email} đã được sử dụng"})

        if RoleCode.STUDENT in dto.roles and not dto.student_code:
            raise HTTPException(
                status_code=400, detail={"message": "Tài khoản sinh viên bắt buộc phải có mã sinh viên"}
            )
        if dto.student_code:
            dup = (
                await self.db.execute(select(StudentProfile).where(StudentProfile.student_code == dto.student_code))
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(
                    status_code=400, detail={"message": f"Mã sinh viên {dto.student_code} đã tồn tại"}
                )

        role_rows = (
            await self.db.execute(select(Role).where(Role.code.in_(dto.roles)))
        ).scalars().all()
        if len(role_rows) != len(set(dto.roles)):
            raise HTTPException(status_code=400, detail={"message": "Có vai trò không tồn tại trong hệ thống"})

        study_class = None
        if dto.class_code:
            study_class = (
                await self.db.execute(select(StudyClass).where(StudyClass.code == dto.class_code))
            ).scalar_one_or_none()
            if not study_class:
                raise HTTPException(status_code=400, detail={"message": f"Không tìm thấy lớp {dto.class_code}"})

        faculty_id = None
        if dto.faculty_id:
            try:
                faculty = await self.db.get(Faculty, uuid.UUID(dto.faculty_id))
            except (ValueError, TypeError):
                faculty = None
            if not faculty:
                raise HTTPException(status_code=400, detail={"message": "Khoa không hợp lệ", "code": "INVALID_FACULTY"})
            faculty_id = faculty.id

        password_hash = await asyncio.to_thread(hash_password, dto.password)
        user = User(
            email=dto.email, full_name=dto.full_name, phone=dto.phone, password_hash=password_hash,
            faculty_id=faculty_id if RoleCode.STUDENT not in dto.roles else None,
        )
        self.db.add(user)
        await self.db.flush()

        for r in role_rows:
            self.db.add(UserRole(user_id=user.id, role_id=r.id, assigned_by=actor_id))

        if RoleCode.STUDENT in dto.roles and dto.student_code:
            self.db.add(
                StudentProfile(
                    user_id=user.id,
                    student_code=dto.student_code,
                    class_id=study_class.id if study_class else None,
                    cohort=dto.cohort,
                    training_system=dto.training_system,
                )
            )
        await self.db.flush()

        await self.audit.log(
            action="USER_CREATE",
            user_id=actor_id,
            entity_type="User",
            entity_id=str(user.id),
            detail={"email": dto.email, "roles": [r.value for r in dto.roles]},
            request=request,
        )
        await self.db.commit()

        return {
            "id": str(user.id),
            "email": user.email,
            "fullName": user.full_name,
            "phone": user.phone,
            "status": user.status,
            "lastLoginAt": user.last_login_at,
            "createdAt": user.created_at,
            "roles": [r.code for r in role_rows],
        }

    async def update_status(self, target_id: str, dto: UpdateUserStatusRequest, actor_id: str,
                             request: Request) -> dict:
        stmt = select(User).options(selectinload(User.roles).selectinload(UserRole.role)).where(User.id == target_id)
        target = (await self.db.execute(stmt)).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})

        if target_id == actor_id and dto.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=400, detail={"message": "Không thể tự khóa tài khoản của chính mình"})

        target_roles = [ur.role.code for ur in target.roles]
        await self._assert_not_last_admin(target_roles, target_id, dto.status)

        from_status = target.status
        target.status = dto.status
        await self.db.flush()

        if dto.status != UserStatus.ACTIVE:
            from app.services.accounts.auth_service import AuthService

            await AuthService(self.db).revoke_all_sessions(target_id)

        await self.audit.log(
            action="USER_STATUS_CHANGE",
            user_id=actor_id,
            entity_type="User",
            entity_id=target_id,
            detail={"from": from_status.value, "to": dto.status.value, "reason": dto.reason},
            request=request,
        )
        await self.db.commit()

        return {
            "id": str(target.id),
            "email": target.email,
            "fullName": target.full_name,
            "phone": target.phone,
            "status": target.status,
            "lastLoginAt": target.last_login_at,
            "createdAt": target.created_at,
            "roles": target_roles,
        }

    async def update_roles(self, target_id: str, dto: UpdateUserRolesRequest, actor_id: str,
                            request: Request) -> dict:
        stmt = select(User).options(selectinload(User.roles).selectinload(UserRole.role)).where(User.id == target_id)
        target = (await self.db.execute(stmt)).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy người dùng"})

        before = [ur.role.code for ur in target.roles]
        if RoleCode.ADMIN in before and RoleCode.ADMIN not in dto.roles:
            await self._assert_not_last_admin(before, target_id, UserStatus.ACTIVE, removing_admin_role=True)

        role_rows = (await self.db.execute(select(Role).where(Role.code.in_(dto.roles)))).scalars().all()
        if len(role_rows) != len(set(dto.roles)):
            raise HTTPException(status_code=400, detail={"message": "Có vai trò không tồn tại trong hệ thống"})

        for ur in list(target.roles):
            await self.db.delete(ur)
        await self.db.flush()
        for r in role_rows:
            self.db.add(UserRole(user_id=target_id, role_id=r.id, assigned_by=actor_id))
        await self.db.flush()

        await self.audit.log(
            action="USER_ROLES_CHANGE",
            user_id=actor_id,
            entity_type="User",
            entity_id=target_id,
            detail={"from": [r.value for r in before], "to": [r.value for r in dto.roles]},
            request=request,
        )
        await self.db.commit()

        return await self.list_users(search=target.email, role=None, status_=None, page=1, page_size=1)

    async def _assert_not_last_admin(self, target_roles: list[RoleCode], target_id: str, next_status: UserStatus,
                                      removing_admin_role: bool = False) -> None:
        losing_admin = RoleCode.ADMIN in target_roles and (next_status != UserStatus.ACTIVE or removing_admin_role)
        if not losing_admin:
            return

        stmt = (
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .join(User.roles)
            .join(UserRole.role)
            .where(User.id != target_id, User.status == UserStatus.ACTIVE, Role.code == RoleCode.ADMIN)
        )
        other_active_admins = (await self.db.execute(stmt)).scalar_one()
        if other_active_admins == 0:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Đây là quản trị viên đang hoạt động cuối cùng. "
                    "Hãy cấp quyền ADMIN cho tài khoản khác trước."
                },
            )

    # ----------------------------------------------------------- audit logs

    async def list_audit_logs(self, *, page: int, page_size: int, action: str | None, user_id: str | None) -> dict:
        stmt = select(AuditLog).options(selectinload(AuditLog.user))
        count_stmt = select(func.count()).select_from(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
            count_stmt = count_stmt.where(AuditLog.user_id == user_id)

        total = (await self.db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()

        items = [
            {
                "id": str(r.id),
                "action": r.action,
                "entityType": r.entity_type,
                "entityId": r.entity_id,
                "detail": r.detail,
                "ipAddress": r.ip_address,
                "createdAt": r.created_at,
                "user": (
                    {"id": str(r.user.id), "email": r.user.email, "fullName": r.user.full_name}
                    if r.user
                    else None
                ),
            }
            for r in rows
        ]
        return {"total": total, "page": page, "pageSize": page_size, "items": items}
