"""Minimal Phase 1 seed: 6 roles + 8 demo users (+ StudentProfile for the 2
students) + 1 class. Just enough to smoke-test login end to end.

Port of the relevant subset of `server/api/prisma/seed.ts`. Idempotent —
upserts on natural keys (role code / user email / class code), same as the
original. The full seed (form templates, courses, schedules, documents) is
Phase 5's `seed.py`.

Run with:  .venv/Scripts/python.exe seed_phase1.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.academic import StudyClass
from app.models.enums import RoleCode
from app.models.users import Role, StudentProfile, User, UserRole
from app.security import hash_password

DEMO_PASSWORD = "Demo@2026"
DEMO_PIN = "135790"

ROLES = [
    ("ADMIN", "Quản trị viên", "Toàn quyền tài khoản, vai trò, audit log, trạng thái dịch vụ"),
    ("ACADEMIC_MANAGER", "Cán bộ quản lý đào tạo", "Nguồn tài liệu RAG, lịch học/lịch thi, duyệt đơn cấp cuối"),
    ("LECTURER", "Giáo viên bộ môn", "Tài liệu giảng dạy, xem lịch môn phụ trách"),
    ("APPROVER", "Cán bộ phê duyệt", "Tiếp nhận và xử lý đơn hành chính"),
    ("STUDENT", "Học viên", "Hỏi đáp, trợ lý học tập, lịch cá nhân, tạo và theo dõi đơn"),
    ("DEPARTMENT_HEAD", "Lãnh đạo Khoa", "Duyệt Đơn xin học bổ sung — cấp duy nhất chỉ đơn này mới có"),
]

USERS = [
    {"email": "admin@hvktcnan.edu.vn", "fullName": "Trần Quốc Khánh", "phone": "0901000001", "roles": ["ADMIN"]},
    {
        "email": "qldt@hvktcnan.edu.vn",
        "fullName": "Nguyễn Thị Bích Ngọc",
        "phone": "0901000002",
        "roles": ["ACADEMIC_MANAGER"],
    },
    {"email": "qlhv@hvktcnan.edu.vn", "fullName": "Phạm Văn Cường", "phone": "0901000003", "roles": ["APPROVER"]},
    {"email": "khoa@hvktcnan.edu.vn", "fullName": "Đỗ Thị Thu Hà", "phone": "0901000006", "roles": ["DEPARTMENT_HEAD"]},
    {
        "email": "gv.lehoanganh@hvktcnan.edu.vn",
        "fullName": "Lê Hoàng Anh",
        "phone": "0901000004",
        "roles": ["LECTURER", "APPROVER"],
    },
    {
        "email": "gv.nguyenvanminh@hvktcnan.edu.vn",
        "fullName": "Nguyễn Văn Minh",
        "phone": "0901000005",
        "roles": ["LECTURER"],
    },
    {
        "email": "sv.nguyenducanh@hvktcnan.edu.vn",
        "fullName": "Nguyễn Đức Anh",
        "phone": "0912000001",
        "roles": ["STUDENT"],
        "student": {
            "studentCode": "B3D15001",
            "dateOfBirth": "2005-03-14",
            "placeOfBirth": "Hà Nội",
            "gender": "Nam",
            "address": "Số 12, phố Nguyễn Trãi, Thanh Xuân, Hà Nội",
            "cohort": "B3",
            "trainingSystem": "Đại học chính quy",
            "enrollYear": 2023,
        },
    },
    {
        "email": "sv.tranthimai@hvktcnan.edu.vn",
        "fullName": "Trần Thị Mai",
        "phone": "0912000002",
        "roles": ["STUDENT"],
        "student": {
            "studentCode": "B3D15002",
            "dateOfBirth": "2005-09-02",
            "placeOfBirth": "Bắc Ninh",
            "gender": "Nữ",
            "address": "Khu 5, phường Võ Cường, TP Bắc Ninh",
            "cohort": "B3",
            "trainingSystem": "Đại học chính quy",
            "enrollYear": 2023,
        },
    },
]


async def upsert_roles(db: AsyncSession) -> dict[str, Role]:
    by_code: dict[str, Role] = {}
    for code, name, desc in ROLES:
        row = (await db.execute(select(Role).where(Role.code == RoleCode(code)))).scalar_one_or_none()
        if row is None:
            row = Role(code=RoleCode(code), name=name, description=desc)
            db.add(row)
            await db.flush()
            print(f"  + role {code}")
        else:
            row.name = name
            row.description = desc
            print(f"  = role {code} (exists)")
        by_code[code] = row
    return by_code


async def upsert_class(db: AsyncSession) -> StudyClass:
    row = (await db.execute(select(StudyClass).where(StudyClass.code == "B3D15"))).scalar_one_or_none()
    if row is None:
        row = StudyClass(
            code="B3D15",
            name="Lớp B3D15 — An toàn thông tin",
            faculty="Khoa Công nghệ thông tin",
            cohort_year=2023,
        )
        db.add(row)
        await db.flush()
        print("  + class B3D15")
    else:
        print("  = class B3D15 (exists)")
    return row


async def upsert_users(db: AsyncSession, roles_by_code: dict[str, Role], study_class: StudyClass) -> None:
    from datetime import date as date_cls

    password_hash = hash_password(DEMO_PASSWORD)
    pin_hash = hash_password(DEMO_PIN)

    for u in USERS:
        user = (await db.execute(select(User).where(User.email == u["email"]))).scalar_one_or_none()
        if user is None:
            user = User(
                email=u["email"],
                full_name=u["fullName"],
                phone=u["phone"],
                password_hash=password_hash,
                signature_pin_hash=pin_hash,
            )
            db.add(user)
            await db.flush()
            print(f"  + user {u['email']}")
        else:
            user.full_name = u["fullName"]
            user.phone = u["phone"]
            print(f"  = user {u['email']} (exists)")

        existing = (await db.execute(select(UserRole).where(UserRole.user_id == user.id))).scalars().all()
        existing_role_ids = {ur.role_id for ur in existing}
        for code in u["roles"]:
            role = roles_by_code[code]
            if role.id not in existing_role_ids:
                db.add(UserRole(user_id=user.id, role_id=role.id))

        student = u.get("student")
        if student:
            sp = (
                await db.execute(select(StudentProfile).where(StudentProfile.user_id == user.id))
            ).scalar_one_or_none()
            dob = date_cls.fromisoformat(student["dateOfBirth"])
            if sp is None:
                sp = StudentProfile(
                    user_id=user.id,
                    student_code=student["studentCode"],
                    class_id=study_class.id,
                    date_of_birth=dob,
                    place_of_birth=student["placeOfBirth"],
                    gender=student["gender"],
                    address=student["address"],
                    cohort=student["cohort"],
                    training_system=student["trainingSystem"],
                    enroll_year=student["enrollYear"],
                )
                db.add(sp)
            else:
                sp.class_id = study_class.id
                sp.cohort = student["cohort"]
                sp.training_system = student["trainingSystem"]

        await db.flush()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        print("Seeding roles...")
        roles_by_code = await upsert_roles(db)
        print("Seeding class...")
        study_class = await upsert_class(db)
        print("Seeding users...")
        await upsert_users(db, roles_by_code, study_class)
        await db.commit()
        print("Done. Demo password for all users:", DEMO_PASSWORD, "| PIN:", DEMO_PIN)


if __name__ == "__main__":
    asyncio.run(main())
