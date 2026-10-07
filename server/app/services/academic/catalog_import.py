"""Nhập danh sách học viên từ CSV (quản lý đào tạo / quản trị): tạo tài khoản mới, cập nhật lớp và họ tên.

Cột (dòng đầu là tên cột, UTF-8): `ma_hv`, `ho_ten`, `email` bắt buộc; `ma_lop`, `khoa_hoc`, `sdt` tùy chọn.

Quy tắc:
  * Mã học viên chưa có → tạo tài khoản STUDENT với mật khẩu ngẫu nhiên. Mật khẩu chỉ trả về MỘT lần trong kết quả
    lúc ghi thật (để quản lý tải về giao cho học viên) và không lưu dạng rõ ở đâu cả.
  * Mã học viên đã có → cập nhật họ tên / lớp / khóa / số điện thoại khi có khác biệt; email không đổi qua tệp
    (nếu khác email hiện có thì báo lỗi dòng đó, tránh gán nhầm người).
  * Chỉ ghi khi không còn dòng lỗi (tất cả hoặc không gì cả); `dryRun` chạy đủ kiểm tra nhưng không ghi.
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
import secrets
import string

from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.core.security import hash_password
from app.models.academic import StudyClass
from app.models.enums import RoleCode
from app.models.users import Role, StudentProfile, User, UserRole

IMPORT_MAX_ROWS = 1000
_REQUIRED = ("ma_hv", "ho_ten", "email")
_COLUMNS = ("ma_hv", "ho_ten", "email", "ma_lop", "khoa_hoc", "sdt")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^0\d{9,10}$")
_ALPHABET = string.ascii_letters.replace("l", "").replace("I", "").replace("O", "") + string.digits.replace("0", "").replace("1", "")


def _password() -> str:
    """10 ký tự, bỏ các ký tự dễ đọc nhầm (l, I, O, 0, 1); luôn có chữ hoa, chữ thường và số."""
    while True:
        pw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        if any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def _bad(message: str, code: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"message": message, "code": code})


class ImportStudentsMixin:
    async def import_students(
        self, user: AuthenticatedUser, *, content: bytes, filename: str | None, dry_run: bool, request: Request | None
    ) -> dict:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise _bad("Tệp phải mã hóa UTF-8", "BAD_ENCODING") from exc
        reader = csv.DictReader(io.StringIO(text))
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        missing = [h for h in _REQUIRED if h not in header]
        if missing:
            raise _bad("Thiếu cột: " + ", ".join(missing) + ". Cột hợp lệ: " + ", ".join(_COLUMNS), "BAD_HEADER")
        rows = list(reader)
        if len(rows) > IMPORT_MAX_ROWS:
            raise _bad(f"Tối đa {IMPORT_MAX_ROWS} dòng mỗi lần", "TOO_MANY_ROWS")

        norm = [{k.strip().lower(): (v or "").strip() for k, v in raw.items() if k} for raw in rows]
        codes = {r.get("ma_hv", "") for r in norm} - {""}
        emails = {r.get("email", "").lower() for r in norm} - {""}
        class_codes = {r.get("ma_lop", "") for r in norm} - {""}

        profiles = {
            sp.student_code: sp
            for sp in (await self.db.execute(select(StudentProfile).where(StudentProfile.student_code.in_(codes)))).scalars()
        } if codes else {}
        users = {u.id: u for u in (await self.db.execute(select(User).where(User.id.in_([p.user_id for p in profiles.values()])))).scalars()} if profiles else {}
        email_owner = {
            e.lower(): uid
            for uid, e in (await self.db.execute(select(User.id, User.email).where(User.email.in_(emails)))).all()
        } if emails else {}
        classes = {
            c.code: c for c in (await self.db.execute(select(StudyClass).where(StudyClass.code.in_(class_codes)))).scalars()
        } if class_codes else {}

        errors: list[dict] = []
        plan: list[dict] = []
        seen_codes: dict[str, int] = {}
        seen_emails: dict[str, int] = {}
        for line, r in enumerate(norm, start=2):
            problems: list[str] = []
            code, name, email = r.get("ma_hv", ""), r.get("ho_ten", ""), r.get("email", "").lower()
            cls_code, cohort, phone = r.get("ma_lop", ""), r.get("khoa_hoc", ""), r.get("sdt", "")
            if not code:
                problems.append("thiếu mã học viên")
            elif code in seen_codes:
                problems.append(f"mã {code} đã xuất hiện ở dòng {seen_codes[code]}")
            else:
                seen_codes[code] = line
            if len(name) < 2:
                problems.append("họ tên quá ngắn hoặc trống")
            if not _EMAIL.match(email):
                problems.append(f"email không hợp lệ ({email or 'trống'})")
            elif email in seen_emails:
                problems.append(f"email {email} đã xuất hiện ở dòng {seen_emails[email]}")
            else:
                seen_emails[email] = line
            if phone and not _PHONE.match(phone):
                problems.append(f"số điện thoại không hợp lệ ({phone})")
            cls = None
            if cls_code:
                cls = classes.get(cls_code)
                if cls is None:
                    problems.append(f"không có lớp mã {cls_code}")

            profile = profiles.get(code) if code else None
            if profile is None:
                owner = email_owner.get(email)
                if owner is not None:
                    problems.append(f"email {email} đã thuộc tài khoản khác")
            else:
                existing = users[profile.user_id]
                if existing.email.lower() != email:
                    problems.append(f"mã {code} đã gắn với email khác ({existing.email}); email không đổi qua tệp")
            if problems:
                errors.append({"line": line, "message": "; ".join(problems)})
                continue
            plan.append({"line": line, "code": code, "name": name, "email": email, "cls": cls, "cohort": cohort or None,
                         "phone": phone or None, "profile": profile})

        # Phân loại: tạo mới / cập nhật / không đổi (để báo cả khi chạy thử).
        created = updated = unchanged = 0
        for p in plan:
            prof = p["profile"]
            if prof is None:
                p["kind"] = "create"
                created += 1
                continue
            u = users[prof.user_id]
            changed = (
                u.full_name != p["name"]
                or (p["phone"] is not None and u.phone != p["phone"])
                or (p["cls"] is not None and prof.class_id != p["cls"].id)
                or (p["cohort"] is not None and prof.cohort != p["cohort"])
            )
            p["kind"] = "update" if changed else "same"
            if changed:
                updated += 1
            else:
                unchanged += 1

        result = {
            "fileName": filename, "totalRows": len(norm), "validRows": len(plan), "errors": errors, "dryRun": dry_run,
            "created": created, "updated": updated, "unchanged": unchanged, "accepted": False, "credentials": [],
        }
        if errors or dry_run:
            result["message"] = (
                f"Phát hiện {len(errors)} dòng lỗi, chưa ghi gì" if errors
                else f"Tệp hợp lệ: sẽ tạo {created} tài khoản, cập nhật {updated}, giữ nguyên {unchanged} (chạy thử, chưa ghi)"
            )
            return result

        role = (await self.db.execute(select(Role).where(Role.code == RoleCode.STUDENT))).scalar_one()
        credentials: list[dict] = []
        for p in plan:
            if p["kind"] == "same":
                continue
            if p["kind"] == "create":
                pw = _password()
                account = User(
                    email=p["email"], full_name=p["name"], phone=p["phone"],
                    password_hash=await asyncio.to_thread(hash_password, pw),
                )
                self.db.add(account)
                await self.db.flush()
                self.db.add(UserRole(user_id=account.id, role_id=role.id, assigned_by=user.id))
                self.db.add(
                    StudentProfile(user_id=account.id, student_code=p["code"],
                                   class_id=p["cls"].id if p["cls"] else None, cohort=p["cohort"])
                )
                credentials.append({"studentCode": p["code"], "fullName": p["name"], "email": p["email"], "password": pw})
                continue
            prof = p["profile"]
            u = users[prof.user_id]
            u.full_name = p["name"]
            if p["phone"] is not None:
                u.phone = p["phone"]
            if p["cls"] is not None:
                prof.class_id = p["cls"].id
            if p["cohort"] is not None:
                prof.cohort = p["cohort"]

        await self.db.flush()
        await self.audit.log(
            action="STUDENTS_IMPORT", user_id=user.id, entity_type="StudentProfile", entity_id=None,
            detail={"fileName": filename, "created": created, "updated": updated, "unchanged": unchanged},
            request=request,
        )
        await self.db.commit()
        result["accepted"] = True
        result["credentials"] = credentials
        result["message"] = f"Đã tạo {created} tài khoản, cập nhật {updated}, giữ nguyên {unchanged}"
        return result
