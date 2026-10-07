"""Nạp thời khóa biểu thật (32 lớp) từ `data/corpus/tkb/` và tạo ~10 tài khoản học viên thử.

Nguồn: `TKB_danh_sach_lop.csv` (lớp, ngành), `TKB_hoc_phan.csv` (học phần của từng lớp: mã, tên, tín chỉ),
`TKB_lich_hoc.csv` (từng buổi: thứ, tiết, tuần, ngày/tháng, ký hiệu học phần).

Dữ liệu nguồn chỉ có tiết, không có giờ, phòng hay giảng viên, nên:
  * Giờ học suy từ tiết (mỗi tiết 50 phút; tiết 1 = 07:00, nghỉ 10 phút sau tiết 3, tiết 7 = 13:30) — giả định,
    cùng quy ước với dữ liệu mẫu hiện có (tiết 1–3 = 07:00–09:30, 4–6 = 09:40–12:10, 7–8 = 13:30–15:10).
  * Phòng ghi "Chưa xếp" (không bao giờ tính là trùng phòng); giảng viên để trống.
  * Học kỳ I năm học 2026–2027; tháng 8–12 là năm 2026, tháng 1 là năm 2027.
  * Khoa của lớp để trống (nguồn chỉ có ngành); tên lớp ghi kèm ngành.
Lớp đã có trong CSDL (vd B3D15 của dữ liệu mẫu) giữ nguyên, không nạp lịch để khỏi lẫn với lịch mẫu. Buổi có ký hiệu học
phần không khớp bảng học phần của lớp bị bỏ qua và được liệt kê.

Chạy lại nhiều lần an toàn (mã buổi `TKB-<lớp>-<số thứ tự>` cố định). Mặc định chỉ in kế hoạch.

    python scripts/import_tkb.py              # xem trước
    python scripts/import_tkb.py --apply      # ghi lớp, môn, lịch và 10 tài khoản thử
    python scripts/import_tkb.py --apply --demo-accounts 0   # không tạo tài khoản
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from sqlalchemy import select  # noqa: E402

from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.academic import Course, Schedule, StudyClass  # noqa: E402
from app.models.enums import RoleCode, ScheduleStatus, SessionType  # noqa: E402
from app.models.users import Role, StudentProfile, User, UserRole  # noqa: E402

TKB_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus" / "tkb"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
YEAR, SEMESTER = "2026-2027", "HK1"
DEMO_PASSWORD = "Demo@2026"
MANAGER_EMAIL = "qldt@hvktcnan.edu.vn"

# Giờ bắt đầu của từng tiết (phút kể từ 00:00); mỗi tiết 50 phút.
_PERIOD_START = {1: 420, 2: 470, 3: 520, 4: 580, 5: 630, 6: 680, 7: 810, 8: 860, 9: 910, 10: 970, 11: 1020, 12: 1070}
_PERIOD_LEN = 50
_WEEKDAY = {"thứ hai": 0, "thứ ba": 1, "thứ tư": 2, "thứ năm": 3, "thứ sáu": 4, "thứ bảy": 5, "chủ nhật": 6}
_MONTH_YEAR = {1: 2027, 8: 2026, 9: 2026, 10: 2026, 11: 2026, 12: 2026}

# Tên mẫu cho tài khoản thử (họ tên giả, không phải người thật).
_DEMO_NAMES = [
    "Nguyễn Minh Khôi", "Trần Thu Hà", "Lê Quang Huy", "Phạm Ngọc Anh", "Hoàng Gia Bảo",
    "Vũ Thanh Tâm", "Đặng Hải Long", "Bùi Khánh Linh", "Đỗ Tuấn Kiệt", "Ngô Phương Thảo",
]


def _read(name: str) -> list[dict]:
    with open(TKB_DIR / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _periods(raw: str) -> tuple[int, int] | None:
    """"3 ÷ 4" → (3, 4); "2" → (2, 2)."""
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    if not nums:
        return None
    return nums[0], nums[-1]


def _at(day: date, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=VN_TZ)


def _nganh_title(nganh: str) -> str:
    """"KỸ THUẬT CAND" → "Kỹ thuật CAND" (giữ nguyên chữ viết tắt CAND)."""
    words = nganh.strip().split()
    out = [w if w == "CAND" else w.lower() for w in words]
    text = " ".join(out)
    return (text[:1].upper() + text[1:]) if text else text


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--demo-accounts", type=int, default=10, help="Số tài khoản học viên thử (0 = không tạo).")
    args = ap.parse_args()

    classes_src = _read("TKB_danh_sach_lop.csv")
    courses_src = _read("TKB_hoc_phan.csv")
    sessions_src = _read("TKB_lich_hoc.csv")

    # (lớp, ký hiệu) -> học phần
    by_symbol: dict[tuple[str, str], dict] = {}
    for r in courses_src:
        by_symbol.setdefault((r["Lop"], r["KH"]), r)

    problems: list[str] = []
    weekday_mismatch = 0
    plan_sessions: list[dict] = []
    seq: Counter[str] = Counter()
    for r in sessions_src:
        lop = r["Lop"]
        seq[lop] += 1
        hp = by_symbol.get((lop, r["HocPhan"]))
        pr = _periods(r["Tiet"])
        if hp is None:
            problems.append(f"{lop} #{seq[lop]}: ký hiệu học phần '{r['HocPhan']}' không có trong bảng học phần của lớp")
            continue
        if pr is None or not (r["Tuan"].isdigit() and r["Thang"].isdigit() and r["Ngay"].isdigit()):
            problems.append(f"{lop} #{seq[lop]}: thiếu tiết/ngày")
            continue
        month = int(r["Thang"])
        year = _MONTH_YEAR.get(month)
        if year is None:
            problems.append(f"{lop} #{seq[lop]}: tháng {month} ngoài học kỳ")
            continue
        try:
            day = date(year, month, int(r["Ngay"]))
        except ValueError:
            problems.append(f"{lop} #{seq[lop]}: ngày không hợp lệ {r['Ngay']}/{month}")
            continue
        if _WEEKDAY.get(r["Thu"].strip().lower()) not in (None, day.weekday()):
            weekday_mismatch += 1  # nguồn ghi thứ không khớp ngày: lấy NGÀY làm chuẩn
        start_p, end_p = pr
        if start_p not in _PERIOD_START or end_p not in _PERIOD_START:
            problems.append(f"{lop} #{seq[lop]}: tiết {r['Tiet']} ngoài bảng giờ")
            continue
        plan_sessions.append({
            "lop": lop, "ext": f"TKB-{lop}-{seq[lop]:04d}", "mahp": hp["MaHP"], "day": day, "week": int(r["Tuan"]),
            "start_p": start_p, "end_p": end_p,
            "starts": _at(day, _PERIOD_START[start_p]),
            "ends": _at(day, _PERIOD_START[end_p] + _PERIOD_LEN),
        })

    course_rows: dict[str, dict] = {}
    for r in courses_src:
        course_rows.setdefault(r["MaHP"], r)

    print(f"Lớp trong nguồn: {len(classes_src)} | học phần khác nhau: {len(course_rows)} | buổi hợp lệ: {len(plan_sessions)}"
          f" | buổi bỏ qua: {len(problems)}")
    print(f"Buổi có thứ không khớp ngày trong nguồn: {weekday_mismatch} (lấy ngày làm chuẩn)")
    print("Ngành:", dict(Counter(_nganh_title(r["Nganh"]) for r in classes_src)))

    async with AsyncSessionLocal() as db:
        have_classes = {c.code: c for c in (await db.execute(select(StudyClass))).scalars()}
        have_courses = {c.code: c for c in (await db.execute(select(Course))).scalars()}
        have_ext = set((await db.execute(select(Schedule.external_id).where(Schedule.academic_year == YEAR, Schedule.semester == SEMESTER))).scalars())

        new_classes = [r for r in classes_src if r["Lop"] not in have_classes]
        kept = [r["Lop"] for r in classes_src if r["Lop"] in have_classes]
        new_courses = [code for code in course_rows if code not in have_courses]
        todo = [s for s in plan_sessions if s["lop"] not in kept and s["ext"] not in have_ext]
        print(f"Lớp mới: {len(new_classes)} | giữ nguyên (đã có, không nạp lịch): {kept}")
        print(f"Môn mới: {len(new_courses)} | buổi mới: {len(todo)}")
        odd_credits = [c for c in course_rows.values() if c["TC"] not in ("1", "2", "3", "4", "5", "6")]
        for c in odd_credits:
            print(f"  tín chỉ bất thường lớp {c['Lop']} môn {c['MaHP']}: '{c['TC']}' → dùng 2")
        for p in problems[:10]:
            print("  bỏ qua:", p)
        if len(problems) > 10:
            print(f"  … và {len(problems) - 10} buổi bỏ qua nữa")
        if not args.apply:
            print("\n(Xem trước — thêm --apply để ghi.)")
            return

        for r in new_classes:
            c = StudyClass(
                code=r["Lop"], name=f"Lớp {r['Lop']} — {_nganh_title(r['Nganh'])}", major=_nganh_title(r["Nganh"])
            )
            db.add(c)
            have_classes[r["Lop"]] = c
        for code in new_courses:
            r = course_rows[code]
            credits = int(r["TC"]) if r["TC"] in ("1", "2", "3", "4", "5", "6") else 2
            c = Course(code=code, name=r["HocPhan"].strip(), credits=credits)
            db.add(c)
            have_courses[code] = c
        await db.flush()

        for s in todo:
            db.add(Schedule(
                external_id=s["ext"], academic_year=YEAR, semester=SEMESTER, class_id=have_classes[s["lop"]].id,
                course_id=have_courses[s["mahp"]].id, session_date=s["day"], week_number=s["week"],
                start_period=s["start_p"], end_period=s["end_p"], starts_at=s["starts"], ends_at=s["ends"],
                room="Chưa xếp", building=None, instructor=None, delivery_mode="Trực tiếp",
                session_type=SessionType.LY_THUYET, status=ScheduleStatus.SCHEDULED,
            ))
        await db.flush()

        made = 0
        if args.demo_accounts > 0:
            role = (await db.execute(select(Role).where(Role.code == RoleCode.STUDENT))).scalar_one()
            manager_id = (await db.execute(select(User.id).where(User.email == MANAGER_EMAIL))).scalar_one_or_none()
            # Trải đều qua các lớp mới nạp (lớp có lịch), mỗi tài khoản một lớp khác nhau.
            with_schedule = [r["Lop"] for r in classes_src if r["Lop"] not in kept]
            step = max(1, len(with_schedule) // max(1, args.demo_accounts))
            chosen = with_schedule[::step][: args.demo_accounts]
            pw_hash = hash_password(DEMO_PASSWORD)  # cùng mật khẩu demo của các tài khoản mẫu
            for i, lop in enumerate(chosen, start=1):
                email = f"sv.demo{i:02d}@hvktcnan.edu.vn"
                if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
                    continue
                code = f"DEMO{i:03d}"
                u = User(email=email, full_name=_DEMO_NAMES[(i - 1) % len(_DEMO_NAMES)], password_hash=pw_hash)
                db.add(u)
                await db.flush()
                db.add(UserRole(user_id=u.id, role_id=role.id, assigned_by=manager_id))
                db.add(StudentProfile(user_id=u.id, student_code=code, class_id=have_classes[lop].id))
                made += 1
                print(f"  tài khoản {email} ({code}) → lớp {lop}")
        await db.commit()
        print(f"\nĐã ghi {len(new_classes)} lớp, {len(new_courses)} môn, {len(todo)} buổi học, {made} tài khoản thử.")


if __name__ == "__main__":
    asyncio.run(main())
