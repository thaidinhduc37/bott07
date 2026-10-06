"""Kết quả học tập: học viên xem điểm theo học kỳ; giảng viên / phòng đào tạo nhập điểm.

Quy ước:
  * Thang 10, đạt từ `PASS_SCORE` (5.0). Điểm học phần do người nhập quyết định — hệ thống không tự suy ra
    từ điểm thành phần vì trọng số từng môn chưa có trong dữ liệu.
  * Trang kết quả của học viên liệt kê MỌI môn có lịch học của lớp trong học kỳ (kể cả chưa có điểm, hiện "-"),
    cộng các môn có điểm nhưng không còn trong lịch.
  * Giảng viên chỉ nhập điểm môn mình phụ trách; ACADEMIC_MANAGER / ADMIN nhập mọi môn. Chỉ nhập cho học viên
    thuộc lớp có lịch môn đó trong học kỳ.
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Schedule, StudyClass
from app.models.enums import NotificationType, RoleCode
from app.models.grades import PASS_SCORE, CourseGrade
from app.models.notifications import Notification
from app.models.users import StudentProfile, User
from app.services.accounts.audit_service import AuditService

SCORE_FIELDS = ("practice", "process", "midterm", "final_exam", "total")
IMPORT_MAX_ROWS = 5000


def _is_manager(user: AuthenticatedUser) -> bool:
    return RoleCode.ADMIN.value in user.roles or RoleCode.ACADEMIC_MANAGER.value in user.roles


def _term_key(year: str, semester: str) -> tuple[str, str]:
    return (year.strip(), semester.strip())


def _term_sort_key(term: tuple[str, str]):
    # Mới nhất trước: năm học (chuỗi "2025-2026" so sánh được) rồi học kỳ.
    return (term[0], term[1])


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _check_score(value, label: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"message": f"{label} phải là số", "code": "INVALID_SCORE"})
    if score != score or score < 0 or score > 10:
        raise HTTPException(
            status_code=400, detail={"message": f"{label} phải nằm trong khoảng 0 đến 10", "code": "INVALID_SCORE"}
        )
    return round(score, 2)


def _parse_uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail={"message": message})


def weighted_average(rows: list[tuple[float, int]]) -> float | None:
    """Điểm trung bình có trọng số tín chỉ; `rows` = [(điểm, tín chỉ)]. Không có dòng nào → None."""
    credits = sum(c for _, c in rows)
    if not rows or credits <= 0:
        return None
    return round(sum(s * c for s, c in rows) / credits, 2)


class GradesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------ học viên

    async def my_results(self, user_id: str) -> dict:
        uid = uuid.UUID(user_id)
        profile = (
            await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == uid))
        ).scalar_one_or_none()

        # Môn theo lịch của lớp: (năm học, học kỳ) → {course_id}
        scheduled: dict[tuple[str, str], set[uuid.UUID]] = {}
        if profile and profile.class_id:
            for model in (Schedule, ExamSchedule):
                for year, sem, cid in (
                    await self.db.execute(
                        select(model.academic_year, model.semester, model.course_id).where(model.class_id == profile.class_id)
                    )
                ).all():
                    scheduled.setdefault(_term_key(year, sem), set()).add(cid)

        grades = (await self.db.execute(select(CourseGrade).where(CourseGrade.student_id == uid))).scalars().all()
        by_cell = {(_term_key(g.academic_year, g.semester), g.course_id): g for g in grades}
        for (term, cid) in by_cell:
            scheduled.setdefault(term, set()).add(cid)

        course_ids = {cid for ids in scheduled.values() for cid in ids}
        courses = {}
        if course_ids:
            courses = {
                c.id: c for c in (await self.db.execute(select(Course).where(Course.id.in_(course_ids)))).scalars().all()
            }

        # Lần học của một môn = thứ tự học kỳ (cũ → mới) mà môn đó có điểm; lần chưa đạt = số học kỳ có điểm < ngưỡng
        # tính đến học kỳ đang xét. Dùng điền sẵn "lần học", "lần thi", "lần thứ" của đơn xin học lại.
        graded_terms: dict[uuid.UUID, list[tuple[tuple[str, str], bool]]] = {}
        for (term_key, cid), g in sorted(by_cell.items(), key=lambda kv: _term_sort_key(kv[0][0])):
            if g.total is not None:
                graded_terms.setdefault(cid, []).append((term_key, g.total >= PASS_SCORE))

        def attempts(cid: uuid.UUID, term_key: tuple[str, str]) -> tuple[int, int]:
            seen = [(t, ok) for t, ok in graded_terms.get(cid, []) if _term_sort_key(t) <= _term_sort_key(term_key)]
            return len(seen), sum(1 for _, ok in seen if not ok)

        terms_out = []
        graded_all: list[tuple[float, int]] = []
        graded_passed: list[tuple[float, int]] = []
        credits_studied = 0
        credits_earned = 0
        for term in sorted(scheduled, key=_term_sort_key, reverse=True):
            items = []
            term_graded: list[tuple[float, int]] = []
            term_credits = 0
            for cid in sorted(scheduled[term], key=lambda x: courses[x].code if x in courses else ""):
                course = courses.get(cid)
                if course is None:
                    continue
                g = by_cell.get((term, cid))
                total = g.total if g else None
                passed = None if total is None else total >= PASS_SCORE
                attempt, failed_attempts = attempts(cid, term) if total is not None else (0, 0)
                items.append(
                    {
                        "attempt": attempt,
                        "failedAttempts": failed_attempts,
                        "courseId": str(course.id),
                        "code": course.code,
                        "name": course.name,
                        "credits": course.credits,
                        "practice": _round(g.practice) if g else None,
                        "process": _round(g.process) if g else None,
                        "midterm": _round(g.midterm) if g else None,
                        "finalExam": _round(g.final_exam) if g else None,
                        "total": _round(total),
                        "passed": passed,
                        "note": g.note if g else None,
                    }
                )
                term_credits += course.credits
                if total is not None:
                    term_graded.append((total, course.credits))
                    graded_all.append((total, course.credits))
                    credits_studied += course.credits
                    if passed:
                        graded_passed.append((total, course.credits))
                        credits_earned += course.credits
            terms_out.append(
                {
                    "academicYear": term[0],
                    "semester": term[1],
                    "credits": term_credits,
                    "gradedCount": len(term_graded),
                    "courseCount": len(items),
                    "gpa": weighted_average(term_graded),
                    "courses": items,
                }
            )

        return {
            "passScore": PASS_SCORE,
            "summary": {
                "creditsStudied": credits_studied,       # tín chỉ của các môn đã có điểm
                "creditsEarned": credits_earned,         # tín chỉ của các môn đạt
                "gpa": weighted_average(graded_all),     # điểm trung bình chung
                "gpaEarned": weighted_average(graded_passed),  # điểm trung bình tích lũy (chỉ môn đạt)
            },
            "terms": terms_out,
        }

    # ------------------------------------------------------------ giảng viên / quản lý

    async def _assert_can_grade(self, user: AuthenticatedUser, course: Course) -> None:
        if _is_manager(user):
            return
        if (
            RoleCode.LECTURER.value in user.roles
            and course.lecturer_id is not None
            and str(course.lecturer_id) == str(user.id)
        ):
            return
        raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền nhập điểm môn học này"})

    async def sections(self, user: AuthenticatedUser) -> dict:
        """Danh sách (môn, lớp, năm học, học kỳ) mà người dùng được nhập điểm, kèm sĩ số và số học viên đã có điểm."""
        stmt = (
            select(Schedule.course_id, Schedule.class_id, Schedule.academic_year, Schedule.semester)
            .join(Course, Course.id == Schedule.course_id)
            .distinct()
        )
        if not _is_manager(user):
            stmt = stmt.where(Course.lecturer_id == user.id)
        rows = (await self.db.execute(stmt)).all()
        if not rows:
            return {"items": []}

        courses = {c.id: c for c in (await self.db.execute(select(Course).where(Course.id.in_({r[0] for r in rows})))).scalars().all()}
        classes = {c.id: c for c in (await self.db.execute(select(StudyClass).where(StudyClass.id.in_({r[1] for r in rows})))).scalars().all()}
        students = {
            cid: n
            for cid, n in (
                await self.db.execute(select(StudentProfile.class_id, func.count()).group_by(StudentProfile.class_id))
            ).all()
            if cid is not None
        }
        items = []
        for cid, clid, year, sem in rows:
            course, cls = courses[cid], classes[clid]
            graded = (
                await self.db.execute(
                    select(func.count())
                    .select_from(CourseGrade)
                    .join(StudentProfile, StudentProfile.user_id == CourseGrade.student_id)
                    .where(
                        CourseGrade.course_id == cid, CourseGrade.academic_year == year, CourseGrade.semester == sem,
                        StudentProfile.class_id == clid, CourseGrade.total.is_not(None),
                    )
                )
            ).scalar_one()
            items.append(
                {
                    "course": {"id": str(course.id), "code": course.code, "name": course.name, "credits": course.credits},
                    "class": {"id": str(cls.id), "code": cls.code, "name": cls.name},
                    "academicYear": year,
                    "semester": sem,
                    "studentCount": students.get(clid, 0),
                    "gradedCount": graded,
                }
            )
        items.sort(key=lambda x: (x["academicYear"], x["semester"], x["course"]["code"], x["class"]["code"]), reverse=False)
        items.sort(key=lambda x: (x["academicYear"], x["semester"]), reverse=True)
        return {"items": items}

    async def _assert_section(self, course_id: uuid.UUID, class_id: uuid.UUID | None, year: str, semester: str) -> None:
        """Học kỳ này phải có lịch môn đó (và của lớp đó nếu chỉ định)."""
        stmt = select(func.count()).select_from(Schedule).where(
            Schedule.course_id == course_id, Schedule.academic_year == year, Schedule.semester == semester
        )
        if class_id is not None:
            stmt = stmt.where(Schedule.class_id == class_id)
        if (await self.db.execute(stmt)).scalar_one() == 0:
            raise HTTPException(
                status_code=400, detail={"message": "Môn này không có lịch học trong học kỳ đã chọn", "code": "NO_SECTION"}
            )

    async def roster(self, user: AuthenticatedUser, *, course_id: str, class_id: str, year: str, semester: str) -> dict:
        cid = _parse_uuid(course_id, "Không tìm thấy môn học")
        clid = _parse_uuid(class_id, "Không tìm thấy lớp")
        course = await self.db.get(Course, cid)
        cls = await self.db.get(StudyClass, clid)
        if not course or not cls:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học hoặc lớp"})
        await self._assert_can_grade(user, course)
        await self._assert_section(cid, clid, year, semester)

        profiles = (
            await self.db.execute(
                select(StudentProfile, User)
                .join(User, User.id == StudentProfile.user_id)
                .where(StudentProfile.class_id == clid)
                .order_by(StudentProfile.student_code.asc())
            )
        ).all()
        grades = {
            g.student_id: g
            for g in (
                await self.db.execute(
                    select(CourseGrade).where(
                        CourseGrade.course_id == cid, CourseGrade.academic_year == year, CourseGrade.semester == semester
                    )
                )
            ).scalars().all()
        }
        return {
            "course": {"id": str(course.id), "code": course.code, "name": course.name, "credits": course.credits},
            "class": {"id": str(cls.id), "code": cls.code, "name": cls.name},
            "academicYear": year,
            "semester": semester,
            "students": [
                {
                    "studentId": str(u.id),
                    "studentCode": p.student_code,
                    "fullName": u.full_name,
                    "practice": _round(grades[u.id].practice) if u.id in grades else None,
                    "process": _round(grades[u.id].process) if u.id in grades else None,
                    "midterm": _round(grades[u.id].midterm) if u.id in grades else None,
                    "finalExam": _round(grades[u.id].final_exam) if u.id in grades else None,
                    "total": _round(grades[u.id].total) if u.id in grades else None,
                    "note": grades[u.id].note if u.id in grades else None,
                }
                for p, u in profiles
            ],
        }

    async def _apply(self, *, user: AuthenticatedUser, course: Course, year: str, semester: str,
                     student_id: uuid.UUID, values: dict, notify: list[tuple[uuid.UUID, str]]) -> str:
        """Ghi một dòng điểm; trả "created" / "updated" / "unchanged"."""
        row = (
            await self.db.execute(
                select(CourseGrade).where(
                    CourseGrade.student_id == student_id, CourseGrade.course_id == course.id,
                    CourseGrade.academic_year == year, CourseGrade.semester == semester,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            if all(values.get(f) is None for f in SCORE_FIELDS) and not values.get("note"):
                return "unchanged"
            row = CourseGrade(
                student_id=student_id, course_id=course.id, academic_year=year, semester=semester, updated_by_id=user.id,
                **{f: values.get(f) for f in SCORE_FIELDS}, note=values.get("note"),
            )
            self.db.add(row)
            if row.total is not None:
                notify.append((student_id, course.name))
            return "created"
        changed = False
        old_total = row.total
        for f in (*SCORE_FIELDS, "note"):
            if f in values and getattr(row, f) != values[f]:
                setattr(row, f, values[f])
                changed = True
        if changed:
            row.updated_by_id = user.id
            if row.total is not None and row.total != old_total:
                notify.append((student_id, course.name))
        return "updated" if changed else "unchanged"

    async def _flush_notifications(self, notify: list[tuple[uuid.UUID, str]]) -> None:
        for student_id, course_name in notify:
            self.db.add(
                Notification(
                    user_id=student_id,
                    type=NotificationType.SYSTEM,
                    title="Có điểm học phần mới",
                    body=f"Điểm học phần môn {course_name} đã được cập nhật.",
                    link_to="/sinh-vien/ket-qua",
                )
            )

    async def save_scores(self, user: AuthenticatedUser, *, course_id: str, year: str, semester: str,
                          items: list[dict], request: Request | None) -> dict:
        cid = _parse_uuid(course_id, "Không tìm thấy môn học")
        course = await self.db.get(Course, cid)
        if not course:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})
        await self._assert_can_grade(user, course)
        await self._assert_section(cid, None, year, semester)

        # Học viên phải thuộc lớp có lịch môn này trong học kỳ.
        allowed = {
            uid
            for (uid,) in (
                await self.db.execute(
                    select(StudentProfile.user_id).where(
                        StudentProfile.class_id.in_(
                            select(Schedule.class_id).where(
                                Schedule.course_id == cid, Schedule.academic_year == year, Schedule.semester == semester
                            )
                        )
                    )
                )
            ).all()
        }
        notify: list[tuple[uuid.UUID, str]] = []
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        course_name = course.name
        for idx, it in enumerate(items, start=1):
            sid = _parse_uuid(str(it.get("studentId")), f"Dòng {idx}: không tìm thấy học viên")
            if sid not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail={"message": f"Dòng {idx}: học viên không thuộc lớp học môn này", "code": "NOT_IN_SECTION"},
                )
            values = {
                "practice": _check_score(it.get("practice"), f"Dòng {idx}: điểm TH"),
                "process": _check_score(it.get("process"), f"Dòng {idx}: điểm QT"),
                "midterm": _check_score(it.get("midterm"), f"Dòng {idx}: điểm GK"),
                "final_exam": _check_score(it.get("finalExam"), f"Dòng {idx}: điểm CK"),
                "total": _check_score(it.get("total"), f"Dòng {idx}: điểm học phần"),
                "note": (it.get("note") or None) if isinstance(it.get("note"), str) else None,
            }
            if values["note"]:
                values["note"] = values["note"].strip()[:300] or None
            counts[await self._apply(user=user, course=course, year=year, semester=semester, student_id=sid, values=values, notify=notify)] += 1

        await self._flush_notifications(notify)
        await self.audit.log(
            action="GRADES_SAVE", user_id=user.id, entity_type="Course", entity_id=str(cid),
            detail={"academicYear": year, "semester": semester, **counts}, request=request,
        )
        await self.db.commit()
        return {"message": "Đã lưu điểm", **counts, "course": course_name}

    # ------------------------------------------------------------ nhập CSV (quản lý)

    COLUMNS = {
        "ma_hv": "student_code", "ma_mon": "course_code", "nam_hoc": "academic_year", "hoc_ky": "semester",
        "th": "practice", "qt": "process", "gk": "midterm", "ck": "final_exam", "diem_hp": "total", "ghi_chu": "note",
    }

    async def import_csv(self, user: AuthenticatedUser, *, content: bytes, filename: str | None, dry_run: bool,
                         request: Request | None) -> dict:
        if not _is_manager(user):
            raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền thực hiện thao tác này"})
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail={"message": "Tệp phải mã hóa UTF-8", "code": "BAD_ENCODING"})
        reader = csv.DictReader(io.StringIO(text))
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        missing = [h for h in ("ma_hv", "ma_mon", "nam_hoc", "hoc_ky") if h not in header]
        if missing:
            raise HTTPException(
                status_code=400,
                detail={"message": "Thiếu cột: " + ", ".join(missing) + ". Cột hợp lệ: " + ", ".join(self.COLUMNS), "code": "BAD_HEADER"},
            )

        errors: list[dict] = []
        parsed: list[dict] = []
        rows = list(reader)
        if len(rows) > IMPORT_MAX_ROWS:
            raise HTTPException(status_code=400, detail={"message": f"Tối đa {IMPORT_MAX_ROWS} dòng mỗi lần", "code": "TOO_MANY_ROWS"})

        codes = {(r.get("ma_hv") or "").strip() for r in rows} - {""}
        course_codes = {(r.get("ma_mon") or "").strip() for r in rows} - {""}
        students = {}
        if codes:
            for sp, in (await self.db.execute(select(StudentProfile).where(StudentProfile.student_code.in_(codes)))).all():
                students[sp.student_code] = sp.user_id
        courses = {}
        if course_codes:
            courses = {c.code: c for c in (await self.db.execute(select(Course).where(Course.code.in_(course_codes)))).scalars().all()}

        for line, raw in enumerate(rows, start=2):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            problems: list[str] = []
            sid = students.get(r.get("ma_hv", ""))
            course = courses.get(r.get("ma_mon", ""))
            if sid is None:
                problems.append(f"không có học viên mã {r.get('ma_hv') or '(trống)'}")
            if course is None:
                problems.append(f"không có môn mã {r.get('ma_mon') or '(trống)'}")
            if not r.get("nam_hoc") or not r.get("hoc_ky"):
                problems.append("thiếu năm học hoặc học kỳ")
            values: dict = {}
            for col, field in self.COLUMNS.items():
                if field in ("student_code", "course_code", "academic_year", "semester"):
                    continue
                if field == "note":
                    values["note"] = r.get(col) or None
                    continue
                try:
                    values[field] = _check_score(r.get(col), col.upper())
                except HTTPException as e:
                    problems.append(e.detail["message"])
            if problems:
                errors.append({"line": line, "message": "; ".join(problems)})
                continue
            parsed.append({"line": line, "student_id": sid, "course": course, "year": r["nam_hoc"], "semester": r["hoc_ky"], "values": values})

        result = {"fileName": filename, "totalRows": len(rows), "validRows": len(parsed), "errors": errors,
                  "dryRun": dry_run, "created": 0, "updated": 0, "unchanged": 0, "accepted": False}
        if errors or dry_run:
            result["message"] = (
                f"Phát hiện {len(errors)} dòng lỗi, chưa ghi gì" if errors else f"Tệp hợp lệ ({len(parsed)} dòng), chưa ghi (chạy thử)"
            )
            return result

        notify: list[tuple[uuid.UUID, str]] = []
        for p in parsed:
            outcome = await self._apply(
                user=user, course=p["course"], year=p["year"], semester=p["semester"], student_id=p["student_id"],
                values=p["values"], notify=notify,
            )
            result[outcome] += 1
        await self._flush_notifications(notify)
        await self.audit.log(
            action="GRADES_IMPORT", user_id=user.id, entity_type="CourseGrade", entity_id=None,
            detail={"fileName": filename, "created": result["created"], "updated": result["updated"]}, request=request,
        )
        await self.db.commit()
        result["accepted"] = True
        result["message"] = f"Đã nhập {result['created']} dòng mới, cập nhật {result['updated']} dòng"
        return result
