"""Sinh dữ liệu THỬ ở quy mô một trường nhiều khoa (15 khoa, ~40 ngành, ~160 lớp, hàng nghìn học viên) để thử tải và giao diện.

Tên khoa, ngành, người và môn đều là GIẢ ĐỊNH để minh họa, không phải số liệu của Học viện.

Ngoài ra (trừ khi dùng `--no-tkb`) các lớp/môn nạp từ thời khóa biểu thật (`import_tkb.py`) được gán TẠM vào khoa demo theo ngành
và môn được gán giảng viên demo của khoa — chỉ để giao diện đầy đủ khi trình diễn; `--remove` trả các gán này về trống.

Mọi bản ghi sinh ra mang dấu hiệu nhận biết để xóa sạch được mà không đụng dữ liệu thật:
  * khoa  `DM-01`…`DM-15`; lớp và môn có mã bắt đầu bằng `DM`;
  * giảng viên (mỗi khoa 6 người, người đầu là trưởng khoa) thuộc các khoa `DM-…`; học viên có mã `DMNNNNN`.
    Email theo tên như tài khoản thật (`gv.nguyenvanan@…`, `sv.tranthuha@…`, trùng thì thêm số), mật khẩu `Demo@2026`.

    python scripts/seed_demo_scale.py                       # xem trước số lượng
    python scripts/seed_demo_scale.py --apply               # sinh dữ liệu (mặc định 20 học viên/lớp)
    python scripts/seed_demo_scale.py --apply --students-per-class 10
    python scripts/seed_demo_scale.py --apply --no-tkb      # không đụng lớp/môn của thời khóa biểu thật
    python scripts/seed_demo_scale.py --remove              # xóa toàn bộ dữ liệu thử đã sinh
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from sqlalchemy import select, text  # noqa: E402

from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.academic import Course, Faculty, Schedule, StudyClass  # noqa: E402
from app.models.enums import RoleCode, ScheduleStatus, SessionType  # noqa: E402
from app.models.users import Role, StudentProfile, User, UserRole  # noqa: E402

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PASSWORD = "Demo@2026"
YEAR, SEMESTER = "2026-2027", "HK1"
FIRST_MONDAY = date(2026, 8, 3)
COHORTS = (2023, 2024, 2025, 2026)
LECTURERS_PER_FACULTY = 6
COURSES_PER_FACULTY = 12
COURSES_PER_CLASS = 4
SESSIONS_PER_COURSE = 12

# (tên khoa, [ngành…]) — giả định minh họa.
FACULTIES: list[tuple[str, list[str]]] = [
    ("Khoa An toàn thông tin", ["An toàn hệ thống thông tin", "An ninh mạng", "Bảo mật ứng dụng"]),
    ("Khoa Công nghệ thông tin", ["Công nghệ phần mềm", "Hệ thống thông tin", "Mạng máy tính"]),
    ("Khoa Khoa học dữ liệu và Trí tuệ nhân tạo", ["Khoa học dữ liệu", "Trí tuệ nhân tạo"]),
    ("Khoa Mật mã", ["Mật mã ứng dụng", "Toán mật mã"]),
    ("Khoa Điện tử - Viễn thông", ["Kỹ thuật viễn thông", "Điện tử vi mạch"]),
    ("Khoa Điều tra số", ["Điều tra tội phạm công nghệ cao", "Pháp y số"]),
    ("Khoa Trinh sát kỹ thuật", ["Trinh sát kỹ thuật", "Giám sát thông tin"]),
    ("Khoa Kỹ thuật máy tính", ["Kỹ thuật máy tính", "Hệ thống nhúng"]),
    ("Khoa Tự động hóa và Điều khiển", ["Tự động hóa", "Robot và hệ thống thông minh"]),
    ("Khoa Hậu cần - Kỹ thuật", ["Hậu cần", "Quản lý trang thiết bị"]),
    ("Khoa Khoa học cơ bản", ["Toán ứng dụng", "Vật lý kỹ thuật"]),
    ("Khoa Lý luận chính trị", ["Giáo dục chính trị"]),
    ("Khoa Ngoại ngữ", ["Tiếng Anh chuyên ngành", "Tiếng Trung chuyên ngành"]),
    ("Khoa Quân sự - Thể chất", ["Giáo dục quốc phòng", "Giáo dục thể chất"]),
    ("Khoa Pháp luật và Quản lý", ["Pháp luật về an ninh mạng", "Quản trị an ninh"]),
]

def _slug(name: str) -> str:
    """"Nguyễn Văn An" → "nguyenvanan" (bỏ dấu, chữ thường, không khoảng trắng)."""
    plain = unicodedata.normalize("NFD", name).replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in plain if ch.isascii() and ch.isalnum()).lower()


def _email(prefix: str, name: str, used: set[str]) -> str:
    base, n = f"{prefix}.{_slug(name)}", 1
    email = f"{base}@hvktcnan.edu.vn"
    while email in used:
        n += 1
        email = f"{base}{n}@hvktcnan.edu.vn"
    used.add(email)
    return email


_HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô", "Dương", "Lý", "Phan", "Trịnh", "Đinh"]
_DEM = ["Văn", "Thị", "Minh", "Quang", "Ngọc", "Thanh", "Hải", "Khánh", "Gia", "Tuấn", "Phương", "Thu", "Đức", "Anh", "Bảo"]
_TEN = ["An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Hiếu", "Hùng", "Khoa", "Lan", "Linh", "Long", "Mai", "Nam", "Phúc",
        "Quân", "Sơn", "Thảo", "Trang", "Việt", "Yến", "Tâm", "Kiên", "Hoa", "Lộc", "Nhi", "Trí", "Uyên", "Vy", "Đạt"]
_TOPICS = ["Nhập môn", "Cơ sở", "Nguyên lý", "Kỹ thuật", "Phân tích", "Thiết kế", "Thực hành", "Chuyên đề", "Ứng dụng",
           "Quản lý", "Đánh giá", "Đồ án"]

# Ngành trong thời khóa biểu thật → số thứ tự khoa demo (giả định, chỉ để trình diễn).
TKB_MAJOR_TO_FACULTY = {
    "Kỹ thuật CAND": 8,
    "Kỹ thuật viễn thông CAND": 5,
    "Công nghệ điện tử và vi mạch bán dẫn": 5,
    "Trinh sát kỹ thuật": 7,
    "Hậu cần CAND": 10,
    "An toàn thông tin CAND": 1,
    "An toàn thông tin": 1,
    "Khoa học dữ liệu và trí tuệ nhân tạo": 3,
    "Công nghệ phần mềm": 2,
}
DEMO_SUFFIX = " (dữ liệu thử)"

# Giờ bắt đầu theo tiết (phút từ 00:00), mỗi tiết 50 phút — cùng quy ước với import_tkb.py.
_BLOCKS = [(1, 3, 420), (4, 6, 580), (7, 9, 810)]


def _name(rng: random.Random) -> str:
    return f"{rng.choice(_HO)} {rng.choice(_DEM)} {rng.choice(_TEN)}"


def _plan() -> list[dict]:
    plan = []
    for fi, (fname, majors) in enumerate(FACULTIES, start=1):
        plan.append({"fi": fi, "name": fname, "majors": majors})
    return plan


async def remove() -> None:
    async with AsyncSessionLocal() as db:
        steps = [
            # Trả về trống các gán tạm của `assign_tkb` (trước khi xóa khoa / tài khoản).
            ("giảng viên buổi học TKB", "UPDATE schedules SET instructor = NULL WHERE external_id LIKE 'TKB-%'"),
            ("khoa chữ của lớp", f"UPDATE classes SET faculty = NULL WHERE faculty LIKE '%{DEMO_SUFFIX}'"),
            ("khoa của lớp", "UPDATE classes SET faculty_id = NULL WHERE faculty_id IN (SELECT id FROM faculties WHERE code LIKE 'DM-%') AND code NOT LIKE 'DM%'"),
            ("khoa của môn TKB", "UPDATE courses SET faculty_id = NULL, lecturer_id = NULL WHERE code NOT LIKE 'DM%' AND faculty_id IN (SELECT id FROM faculties WHERE code LIKE 'DM-%')"),
            ("buổi thi", "DELETE FROM exam_schedules WHERE class_id IN (SELECT id FROM classes WHERE code LIKE 'DM%')"),
            ("buổi học", "DELETE FROM schedules WHERE class_id IN (SELECT id FROM classes WHERE code LIKE 'DM%')"),
            ("điểm", "DELETE FROM course_grades WHERE course_id IN (SELECT id FROM courses WHERE code LIKE 'DM%')"),
            (
                "tài khoản",
                "DELETE FROM users WHERE faculty_id IN (SELECT id FROM faculties WHERE code LIKE 'DM-%') "
                "OR id IN (SELECT user_id FROM student_profiles WHERE student_code LIKE 'DM%') "
                "OR email LIKE 'dm.%@hvktcnan.edu.vn'",  # kiểu email cũ của bản đầu tiên
            ),
            ("môn", "DELETE FROM courses WHERE code LIKE 'DM%'"),
            ("lớp", "DELETE FROM classes WHERE code LIKE 'DM%'"),
            ("khoa", "DELETE FROM faculties WHERE code LIKE 'DM-%'"),
        ]
        for label, sql in steps:
            res = await db.execute(text(sql))
            print(f"  xóa {res.rowcount} {label}")
        await db.commit()
    print("Đã xóa dữ liệu thử.")


async def assign_tkb(db, faculties: dict[int, Faculty], lecturers: dict[int, list[User]]) -> None:
    """Gán tạm lớp/môn của thời khóa biểu thật vào khoa demo theo ngành; môn được gán giảng viên demo của khoa."""
    classes = (await db.execute(select(StudyClass).where(StudyClass.faculty_id.is_(None), StudyClass.code.not_like("DM%")))).scalars().all()
    by_class: dict = {}
    n_cls = 0
    for c in classes:
        fi = TKB_MAJOR_TO_FACULTY.get(c.major or "")
        if fi is None or fi not in faculties:
            continue
        c.faculty_id, c.faculty = faculties[fi].id, faculties[fi].name
        by_class[c.id] = fi
        n_cls += 1
    await db.flush()

    pairs = (await db.execute(select(Schedule.course_id, Schedule.class_id).where(Schedule.external_id.like("TKB-%")).distinct())).all()
    first_faculty: dict = {}
    for course_id, class_id in pairs:
        if class_id in by_class:
            first_faculty.setdefault(course_id, by_class[class_id])
    courses = {c.id: c for c in (await db.execute(select(Course).where(Course.id.in_(list(first_faculty))))).scalars()} if first_faculty else {}
    rr: dict[int, int] = {}
    n_course = 0
    for cid, fi in first_faculty.items():
        course = courses[cid]
        if course.faculty_id is not None or course.lecturer_id is not None:
            continue
        people = lecturers[fi]
        lecturer = people[rr.get(fi, 0) % len(people)]
        rr[fi] = rr.get(fi, 0) + 1
        course.faculty_id, course.lecturer_id = faculties[fi].id, lecturer.id
        await db.execute(
            text("UPDATE schedules SET instructor = :n WHERE course_id = :c AND external_id LIKE 'TKB-%' AND instructor IS NULL"),
            {"n": lecturer.full_name, "c": cid},
        )
        n_course += 1
    print(f"  gán tạm {n_cls} lớp thật vào khoa demo, {n_course} môn thật vào khoa + giảng viên demo")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--students-per-class", type=int, default=20)
    ap.add_argument("--no-tkb", action="store_true", help="Không gán lớp/môn của thời khóa biểu thật vào khoa demo.")
    args = ap.parse_args()

    if args.remove:
        await remove()
        return

    plan = _plan()
    n_major = sum(len(p["majors"]) for p in plan)
    n_class = n_major * len(COHORTS)
    n_students = n_class * args.students_per_class
    n_lect = len(plan) * LECTURERS_PER_FACULTY
    n_course = len(plan) * COURSES_PER_FACULTY
    n_sessions = n_class * COURSES_PER_CLASS * SESSIONS_PER_COURSE
    print(f"Sẽ sinh: {len(plan)} khoa, {n_major} ngành, {n_class} lớp, {n_students} học viên, {n_lect} giảng viên "
          f"({len(plan)} trưởng khoa), {n_course} môn, {n_sessions} buổi học.")
    if not args.apply:
        print("(Xem trước — thêm --apply để ghi; --remove để xóa dữ liệu thử.)")
        return

    rng = random.Random(20260807)
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(Faculty.id).where(Faculty.code == "DM-01"))).first():
            print("Dữ liệu thử đã có (khoa DM-01). Chạy với --remove trước nếu muốn sinh lại.")
            return
        roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
        pw_hash = hash_password(PASSWORD)  # băm một lần, dùng chung (tài khoản thử)
        lecturers_by_faculty: dict[int, list[User]] = {}
        faculties: dict[int, Faculty] = {}
        lect_no = 0
        used_emails = set((await db.execute(select(User.email))).scalars())

        for p in plan:
            # Tên khoa phải duy nhất: thêm hậu tố để không đụng khoa thật cùng tên.
            fac = Faculty(code=f"DM-{p['fi']:02d}", name=f"{p['name']}{DEMO_SUFFIX}")
            db.add(fac)
            await db.flush()
            faculties[p["fi"]] = fac
            people: list[User] = []
            for j in range(LECTURERS_PER_FACULTY):
                lect_no += 1
                full_name = _name(rng)
                u = User(email=_email("gv", full_name, used_emails), full_name=full_name, password_hash=pw_hash,
                         faculty_id=fac.id)
                db.add(u)
                await db.flush()
                db.add(UserRole(user_id=u.id, role_id=roles[RoleCode.LECTURER].id))
                if j == 0:  # người đầu là trưởng khoa
                    db.add(UserRole(user_id=u.id, role_id=roles[RoleCode.DEPARTMENT_HEAD].id))
                    fac.head_id = u.id
                people.append(u)
            lecturers_by_faculty[p["fi"]] = people
        await db.flush()
        print(f"  {len(faculties)} khoa, {lect_no} giảng viên")

        courses_by_faculty: dict[int, list[Course]] = {}
        for p in plan:
            cs: list[Course] = []
            for k in range(COURSES_PER_FACULTY):
                topic = _TOPICS[k % len(_TOPICS)]
                major = p["majors"][k % len(p["majors"])]
                c = Course(code=f"DM{p['fi']:02d}-{k + 1:02d}", name=f"{topic} {major.lower()}", credits=2 + (k % 2),
                           faculty_id=faculties[p["fi"]].id,
                           lecturer_id=lecturers_by_faculty[p["fi"]][k % LECTURERS_PER_FACULTY].id)
                db.add(c)
                cs.append(c)
            courses_by_faculty[p["fi"]] = cs
        await db.flush()
        print(f"  {n_course} môn")

        student_no = 0
        classes_made = sessions_made = 0
        for p in plan:
            fac = faculties[p["fi"]]
            for mi, major in enumerate(p["majors"]):
                for cohort in COHORTS:
                    code = f"DM{p['fi']:02d}{chr(65 + mi)}K{cohort % 100}"
                    cls = StudyClass(code=code, name=f"Lớp {code} — {major}", faculty=fac.name, faculty_id=fac.id,
                                     cohort_year=cohort, major=major)
                    db.add(cls)
                    await db.flush()
                    classes_made += 1
                    for _ in range(args.students_per_class):
                        student_no += 1
                        full_name = _name(rng)
                        u = User(email=_email("sv", full_name, used_emails), full_name=full_name, password_hash=pw_hash)
                        db.add(u)
                        await db.flush()
                        db.add(UserRole(user_id=u.id, role_id=roles[RoleCode.STUDENT].id))
                        db.add(StudentProfile(user_id=u.id, student_code=f"DM{student_no:05d}", class_id=cls.id,
                                              cohort=f"K{cohort % 100}"))
                    # Mỗi lớp học COURSES_PER_CLASS môn của khoa, mỗi môn SESSIONS_PER_COURSE buổi, mỗi tuần một buổi.
                    chosen = rng.sample(courses_by_faculty[p["fi"]], COURSES_PER_CLASS)
                    for ci, course in enumerate(chosen):
                        weekday = (ci + mi) % 5  # thứ 2–6
                        sp, ep, minute = _BLOCKS[(ci + cohort) % len(_BLOCKS)]
                        lecturer = next(u for u in lecturers_by_faculty[p["fi"]] if u.id == course.lecturer_id)
                        for w in range(SESSIONS_PER_COURSE):
                            day = FIRST_MONDAY + timedelta(weeks=w, days=weekday)
                            start = datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=VN_TZ)
                            end = start + timedelta(minutes=50 * (ep - sp + 1))
                            db.add(Schedule(
                                external_id=f"DM-{code}-{ci + 1}-{w + 1:02d}", academic_year=YEAR, semester=SEMESTER,
                                class_id=cls.id, course_id=course.id, session_date=day, week_number=w + 1,
                                start_period=sp, end_period=ep, starts_at=start, ends_at=end, room="Chưa xếp",
                                instructor=lecturer.full_name, delivery_mode="Trực tiếp",
                                session_type=SessionType.LY_THUYET, status=ScheduleStatus.SCHEDULED,
                            ))
                            sessions_made += 1
                    await db.flush()
            print(f"  {p['name']}: xong")
        if not args.no_tkb:
            await assign_tkb(db, faculties, lecturers_by_faculty)
        await db.commit()
        print(f"\nĐã sinh {classes_made} lớp, {student_no} học viên, {sessions_made} buổi học. "
              f"Xóa bằng: python scripts/seed_demo_scale.py --remove")


if __name__ == "__main__":
    asyncio.run(main())
