"""Khoa: thực thể, trưởng khoa, giảng viên thuộc khoa, phân công môn trong phạm vi khoa.

Phân quyền:
  * ADMIN, ACADEMIC_MANAGER — toàn quyền.
  * DEPARTMENT_HEAD — chỉ đọc và phân công trong khoa mà `faculties.head_id` là mình. Khoa khác
    trả 404 (không lộ là khoa có tồn tại).
"""

from __future__ import annotations

import re
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import Course, Faculty, StudyClass
from app.models.enums import NotificationType, RoleCode, UserStatus
from app.models.notifications import Notification
from app.models.users import Role, StudentProfile, User, UserRole
from app.schemas.faculty import AssignCourseLecturerDto, CreateFacultyDto, UpdateFacultyDto
from app.services.accounts.audit_service import AuditService

_CODE_RE = re.compile(r"^[A-Z0-9_-]{1,20}$")
_NOT_FOUND = {"message": "Không tìm thấy khoa"}


def _uuid(value: str, message: dict | None = None) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail=message or _NOT_FOUND)


def _is_manager(user: AuthenticatedUser) -> bool:
    return RoleCode.ADMIN.value in user.roles or RoleCode.ACADEMIC_MANAGER.value in user.roles


def _user_ref(u: User | None) -> dict | None:
    return {"id": str(u.id), "fullName": u.full_name, "email": u.email} if u else None


class FacultyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------ truy cập

    async def _get(self, faculty_id: str, user: AuthenticatedUser, *, manager_only: bool = False) -> Faculty:
        fid = _uuid(faculty_id)
        row = await self.db.get(Faculty, fid)
        if not row:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        if _is_manager(user):
            return row
        if manager_only:
            raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền thực hiện thao tác này"})
        if RoleCode.DEPARTMENT_HEAD.value in user.roles and row.head_id is not None and str(row.head_id) == str(user.id):
            return row
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    async def _users_with_role(self, role: RoleCode) -> list[User]:
        stmt = (
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == role, User.status == UserStatus.ACTIVE)
            .order_by(User.full_name.asc())
        )
        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def _has_role(self, user_id: uuid.UUID, role: RoleCode) -> bool:
        stmt = (
            select(func.count())
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .join(User, User.id == UserRole.user_id)
            .where(UserRole.user_id == user_id, Role.code == role, User.status == UserStatus.ACTIVE)
        )
        return (await self.db.execute(stmt)).scalar_one() > 0

    # ------------------------------------------------------------ trình bày

    async def _item(self, f: Faculty) -> dict:
        fid = f.id
        head = await self.db.get(User, f.head_id) if f.head_id else None
        n_classes = (await self.db.execute(select(func.count()).select_from(StudyClass).where(StudyClass.faculty_id == fid))).scalar_one()
        n_courses = (await self.db.execute(select(func.count()).select_from(Course).where(Course.faculty_id == fid))).scalar_one()
        n_lecturers = (
            await self.db.execute(
                select(func.count(func.distinct(User.id)))
                .select_from(User)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(User.faculty_id == fid, Role.code == RoleCode.LECTURER)
            )
        ).scalar_one()
        n_students = (
            await self.db.execute(
                select(func.count())
                .select_from(StudentProfile)
                .join(StudyClass, StudyClass.id == StudentProfile.class_id)
                .where(StudyClass.faculty_id == fid)
            )
        ).scalar_one()
        return {
            "id": str(f.id),
            "code": f.code,
            "name": f.name,
            "head": _user_ref(head),
            "classCount": n_classes,
            "courseCount": n_courses,
            "lecturerCount": n_lecturers,
            "studentCount": n_students,
        }

    # ------------------------------------------------------------ danh sách

    async def list(self, user: AuthenticatedUser) -> dict:
        stmt = select(Faculty).order_by(Faculty.name.asc())
        if not _is_manager(user):
            stmt = stmt.where(Faculty.head_id == user.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return {"items": [await self._item(f) for f in rows]}

    async def head_candidates(self) -> dict:
        return {"items": [_user_ref(u) for u in await self._users_with_role(RoleCode.DEPARTMENT_HEAD)]}

    async def lecturer_candidates(self, user: AuthenticatedUser) -> dict:
        own: uuid.UUID | None = None
        if not _is_manager(user):
            own = (
                await self.db.execute(select(Faculty.id).where(Faculty.head_id == user.id))
            ).scalar_one_or_none()
        names = {fid: n for fid, n in (await self.db.execute(select(Faculty.id, Faculty.name))).all()}
        items = []
        for u in await self._users_with_role(RoleCode.LECTURER):
            # Trưởng khoa chỉ chọn được người chưa có khoa hoặc đã thuộc khoa mình.
            if own is not None and u.faculty_id not in (None, own):
                continue
            items.append(
                {
                    "id": str(u.id),
                    "fullName": u.full_name,
                    "email": u.email,
                    "facultyId": str(u.faculty_id) if u.faculty_id else None,
                    "facultyName": names.get(u.faculty_id) if u.faculty_id else None,
                }
            )
        return {"items": items}

    # ------------------------------------------------------------ CRUD

    async def _validate_head(self, head_id: str | None) -> User | None:
        if head_id is None:
            return None
        try:
            uid = uuid.UUID(head_id)
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(status_code=400, detail={"message": "Trưởng khoa không hợp lệ", "code": "INVALID_HEAD"})
        u = await self.db.get(User, uid)
        if not u or u.status != UserStatus.ACTIVE or not await self._has_role(uid, RoleCode.DEPARTMENT_HEAD):
            raise HTTPException(status_code=400, detail={"message": "Trưởng khoa không hợp lệ", "code": "INVALID_HEAD"})
        return u

    async def _check_unique(self, code: str | None, name: str | None, exclude: uuid.UUID | None) -> None:
        if code is not None:
            stmt = select(Faculty.id).where(Faculty.code == code)
            if exclude:
                stmt = stmt.where(Faculty.id != exclude)
            if (await self.db.execute(stmt)).first():
                raise HTTPException(
                    status_code=409, detail={"message": f"Đã tồn tại khoa có mã {code}", "code": "FACULTY_CODE_TAKEN"}
                )
        if name is not None:
            stmt = select(Faculty.id).where(func.lower(Faculty.name) == name.lower())
            if exclude:
                stmt = stmt.where(Faculty.id != exclude)
            if (await self.db.execute(stmt)).first():
                raise HTTPException(
                    status_code=409, detail={"message": f"Đã tồn tại khoa tên {name}", "code": "FACULTY_NAME_TAKEN"}
                )

    async def create(self, dto: CreateFacultyDto, user: AuthenticatedUser, request: Request | None) -> dict:
        code = dto.code.strip().upper()
        if not _CODE_RE.match(code):
            raise HTTPException(
                status_code=400,
                detail={"message": "Mã khoa chỉ gồm chữ hoa, số, dấu gạch ngang hoặc gạch dưới (1–20 ký tự)"},
            )
        name = dto.name.strip()
        await self._check_unique(code, name, None)
        head = await self._validate_head(dto.head_id)
        row = Faculty(code=code, name=name, head_id=head.id if head else None)
        self.db.add(row)
        await self.db.flush()
        new_id = row.id
        if head:
            head.faculty_id = new_id
        await self.audit.log(
            action="FACULTY_CREATE", user_id=user.id, entity_type="Faculty", entity_id=str(new_id),
            detail={"code": code, "name": name}, request=request,
        )
        await self.db.commit()
        return await self._item(await self.db.get(Faculty, new_id))

    async def update(self, faculty_id: str, dto: UpdateFacultyDto, user: AuthenticatedUser, request: Request | None) -> dict:
        row = await self._get(faculty_id, user, manager_only=True)
        fid = row.id
        payload = dto.model_dump(exclude_unset=True)
        changes: dict = {}

        if "code" in payload:
            code = (payload["code"] or "").strip().upper()
            if not _CODE_RE.match(code):
                raise HTTPException(
                    status_code=400,
                    detail={"message": "Mã khoa chỉ gồm chữ hoa, số, dấu gạch ngang hoặc gạch dưới (1–20 ký tự)"},
                )
            if code != row.code:
                await self._check_unique(code, None, fid)
                changes["code"] = {"from": row.code, "to": code}
                row.code = code
        if "name" in payload:
            name = (payload["name"] or "").strip() or row.name
            if name != row.name:
                await self._check_unique(None, name, fid)
                changes["name"] = {"from": row.name, "to": name}
                row.name = name
                # Tên khoa dạng chữ ở lớp phải đi theo tên mới.
                classes = (await self.db.execute(select(StudyClass).where(StudyClass.faculty_id == fid))).scalars().all()
                for c in classes:
                    c.faculty = name
        if "head_id" in payload:
            head = await self._validate_head(payload["head_id"])
            new_head_id = head.id if head else None
            if new_head_id != row.head_id:
                changes["headId"] = {
                    "from": str(row.head_id) if row.head_id else None,
                    "to": str(new_head_id) if new_head_id else None,
                }
                row.head_id = new_head_id
                if head:
                    head.faculty_id = fid

        if changes:
            await self.db.flush()
            await self.audit.log(
                action="FACULTY_UPDATE", user_id=user.id, entity_type="Faculty", entity_id=str(fid),
                detail=changes, request=request,
            )
            await self.db.commit()
        return await self._item(await self.db.get(Faculty, fid))

    async def delete(self, faculty_id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        row = await self._get(faculty_id, user, manager_only=True)
        fid = row.id
        n_classes = (await self.db.execute(select(func.count()).select_from(StudyClass).where(StudyClass.faculty_id == fid))).scalar_one()
        n_courses = (await self.db.execute(select(func.count()).select_from(Course).where(Course.faculty_id == fid))).scalar_one()
        n_users = (await self.db.execute(select(func.count()).select_from(User).where(User.faculty_id == fid))).scalar_one()
        # Trưởng khoa tự thuộc khoa mình nên không tính là "đang dùng".
        if row.head_id is not None:
            n_users = max(0, n_users - 1)
        if n_classes or n_courses or n_users:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Khoa còn {n_classes} lớp, {n_courses} môn và {n_users} giảng viên nên chưa xóa được",
                    "code": "FACULTY_IN_USE",
                },
            )
        await self.db.delete(row)
        await self.audit.log(
            action="FACULTY_DELETE", user_id=user.id, entity_type="Faculty", entity_id=str(fid), request=request,
        )
        await self.db.commit()
        return {"message": "Đã xóa khoa"}

    # ------------------------------------------------------------ tổng quan

    async def overview(self, faculty_id: str, user: AuthenticatedUser) -> dict:
        f = await self._get(faculty_id, user)
        fid = f.id
        student_counts = {
            cid: n
            for cid, n in (
                await self.db.execute(select(StudentProfile.class_id, func.count()).group_by(StudentProfile.class_id))
            ).all()
            if cid is not None
        }
        classes = (
            await self.db.execute(select(StudyClass).where(StudyClass.faculty_id == fid).order_by(StudyClass.code.asc()))
        ).scalars().all()
        courses = (await self.db.execute(select(Course).where(Course.faculty_id == fid).order_by(Course.code.asc()))).scalars().all()
        lecturer_ids = {c.lecturer_id for c in courses if c.lecturer_id}
        lecturers_by_id = {
            u.id: u
            for u in (
                (await self.db.execute(select(User).where(User.id.in_(lecturer_ids)))).scalars().all() if lecturer_ids else []
            )
        }
        members = [
            u
            for u in await self._users_with_role(RoleCode.LECTURER)
            if u.faculty_id == fid
        ]
        course_counts = {
            lid: n
            for lid, n in (
                await self.db.execute(
                    select(Course.lecturer_id, func.count())
                    .where(Course.faculty_id == fid, Course.lecturer_id.is_not(None))
                    .group_by(Course.lecturer_id)
                )
            ).all()
        }
        return {
            "faculty": await self._item(f),
            "classes": [
                {
                    "id": str(c.id), "code": c.code, "name": c.name, "cohortYear": c.cohort_year,
                    "studentCount": student_counts.get(c.id, 0),
                }
                for c in classes
            ],
            "courses": [
                {
                    "id": str(c.id), "code": c.code, "name": c.name, "credits": c.credits,
                    "lecturer": _user_ref(lecturers_by_id.get(c.lecturer_id)) if c.lecturer_id else None,
                }
                for c in courses
            ],
            "lecturers": [
                {"id": str(u.id), "fullName": u.full_name, "email": u.email, "courseCount": course_counts.get(u.id, 0)}
                for u in members
            ],
            "unassignedCourseCount": sum(1 for c in courses if c.lecturer_id is None),
        }

    # ------------------------------------------------------------ giảng viên trong khoa

    async def add_lecturer(self, faculty_id: str, user_id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        f = await self._get(faculty_id, user)
        fid = f.id
        uid = _uuid(user_id, {"message": "Không tìm thấy giảng viên"})
        target = await self.db.get(User, uid)
        if not target or target.status != UserStatus.ACTIVE or not await self._has_role(uid, RoleCode.LECTURER):
            raise HTTPException(
                status_code=400, detail={"message": "Người này không phải giảng viên đang hoạt động", "code": "INVALID_LECTURER"}
            )
        if target.faculty_id not in (None, fid) and not _is_manager(user):
            raise HTTPException(
                status_code=409,
                detail={"message": "Giảng viên đang thuộc khoa khác", "code": "LECTURER_IN_OTHER_FACULTY"},
            )
        previous = str(target.faculty_id) if target.faculty_id else None
        target.faculty_id = fid
        await self.audit.log(
            action="FACULTY_LECTURER_ADD", user_id=user.id, entity_type="Faculty", entity_id=str(fid),
            detail={"lecturerId": str(uid), "previousFacultyId": previous}, request=request,
        )
        await self.db.commit()
        return {"message": "Đã đưa giảng viên vào khoa"}

    async def remove_lecturer(self, faculty_id: str, user_id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        f = await self._get(faculty_id, user)
        fid = f.id
        uid = _uuid(user_id, {"message": "Không tìm thấy giảng viên"})
        target = await self.db.get(User, uid)
        if not target or target.faculty_id != fid:
            raise HTTPException(status_code=404, detail={"message": "Giảng viên không thuộc khoa này"})
        courses = (
            await self.db.execute(select(Course).where(Course.faculty_id == fid, Course.lecturer_id == uid))
        ).scalars().all()
        n = len(courses)
        for c in courses:
            c.lecturer_id = None
        target.faculty_id = None
        await self.audit.log(
            action="FACULTY_LECTURER_REMOVE", user_id=user.id, entity_type="Faculty", entity_id=str(fid),
            detail={"lecturerId": str(uid), "unassignedCourses": n}, request=request,
        )
        await self.db.commit()
        return {"message": "Đã bỏ giảng viên khỏi khoa", "unassignedCourses": n}

    # ------------------------------------------------------------ phân công môn

    async def assign_course_lecturer(
        self, faculty_id: str, course_id: str, dto: AssignCourseLecturerDto, user: AuthenticatedUser, request: Request | None
    ) -> dict:
        f = await self._get(faculty_id, user)
        fid = f.id
        cid = _uuid(course_id, {"message": "Không tìm thấy môn học"})
        course = await self.db.get(Course, cid)
        if not course or course.faculty_id != fid:
            raise HTTPException(status_code=404, detail={"message": "Môn học không thuộc khoa này"})

        new_lecturer: User | None = None
        if dto.lecturer_id is not None:
            lid = _uuid(dto.lecturer_id, {"message": "Không tìm thấy giảng viên"})
            new_lecturer = await self.db.get(User, lid)
            if not new_lecturer or new_lecturer.status != UserStatus.ACTIVE or not await self._has_role(lid, RoleCode.LECTURER):
                raise HTTPException(
                    status_code=400, detail={"message": "Giảng viên không hợp lệ", "code": "INVALID_LECTURER"}
                )
            # Trưởng khoa chỉ phân công người trong khoa mình; quản lý đào tạo / quản trị thì không bị ràng buộc.
            if not _is_manager(user) and new_lecturer.faculty_id != fid:
                raise HTTPException(
                    status_code=403,
                    detail={"message": "Chỉ phân công được giảng viên thuộc khoa này", "code": "LECTURER_NOT_IN_FACULTY"},
                )

        new_id = new_lecturer.id if new_lecturer else None
        changed = new_id != course.lecturer_id
        old_id = course.lecturer_id
        course_name = course.name
        course.lecturer_id = new_id
        if changed:
            if new_id:
                self.db.add(
                    Notification(
                        user_id=new_id,
                        type=NotificationType.SYSTEM,
                        title="Phân công môn học mới",
                        body=f"Bạn được phân công phụ trách môn {course_name}",
                        link_to="/can-bo/lich",
                    )
                )
            await self.audit.log(
                action="FACULTY_COURSE_ASSIGN", user_id=user.id, entity_type="Course", entity_id=str(cid),
                detail={"facultyId": str(fid), "from": str(old_id) if old_id else None, "to": str(new_id) if new_id else None},
                request=request,
            )
        result = {
            "id": str(cid), "code": course.code, "name": course_name, "credits": course.credits,
            "lecturer": _user_ref(new_lecturer),
        }
        await self.db.commit()
        return result
