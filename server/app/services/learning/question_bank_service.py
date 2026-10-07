"""Ngân hàng câu hỏi: giảng viên nhập câu trắc nghiệm cho môn mình phụ trách (CSV); học viên ôn bằng cách rút ngẫu nhiên.

Hai định dạng tệp (UTF-8): GIFT của Moodle (mặc định, số đáp án tùy ý, xem `question_gift.py`) và CSV với cột
`cau_hoi`, `a`, `b`, `dap_an` bắt buộc; `c`..`j`, `giai_thich`, `chuong` tùy chọn (đáp án phải liền nhau).

Quy tắc:
  * Giảng viên chỉ nhập / xem / xóa câu của môn có `courses.lecturer_id` là mình; quản lý đào tạo và quản trị: mọi môn.
    Môn không thuộc phạm vi trả 404 như môn không tồn tại.
  * Chỉ ghi khi không còn dòng lỗi; câu trùng (cùng nội dung + đáp án) với câu đã có hoặc đã nhập thì bỏ qua, không lỗi.
  * Học viên không bao giờ nhận đáp án trước khi nộp bài (cùng đường `LearningService._present`).
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import Course
from app.models.enums import RoleCode
from app.models.learning import BankQuestion
from app.services.accounts.audit_service import AuditService
from app.services.learning.question_gift import parse_gift

IMPORT_MAX_ROWS = 500
BANK_MAX_PER_COURSE = 2000
MAX_OPTIONS = 10
_LETTERS = "abcdefghij"
_REQUIRED = ("cau_hoi", "a", "b", "dap_an")  # chỉ cho CSV
_LIMITS = {"cau_hoi": 1000, "option": 300, "giai_thich": 2000, "chuong": 100}


def question_hash(question: str, options: list[str]) -> str:
    """Giống `LearningService._question_hash` (đặt ở đây để tránh import vòng)."""
    raw = question.strip().lower() + "\n" + "\n".join(o.strip().lower() for o in options)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _bad(message: str, code: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"message": message, "code": code})


def _is_manager(user: AuthenticatedUser) -> bool:
    return RoleCode.ADMIN.value in user.roles or RoleCode.ACADEMIC_MANAGER.value in user.roles


class QuestionBankService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # ----------------------------------------------------------------- phạm vi

    async def _course(self, user: AuthenticatedUser, course_id: str) -> Course:
        try:
            cid = uuid.UUID(course_id)
        except (ValueError, TypeError):
            cid = None
        course = await self.db.get(Course, cid) if cid else None
        if course is None or (not _is_manager(user) and str(course.lecturer_id) != str(user.id)):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy môn học"})
        return course

    async def courses(self, user: AuthenticatedUser) -> dict:
        """Các môn người dùng được quản lý ngân hàng câu hỏi, kèm số câu."""
        stmt = select(Course).order_by(Course.code.asc())
        if not _is_manager(user):
            stmt = stmt.where(Course.lecturer_id == uuid.UUID(user.id))
        rows = (await self.db.execute(stmt)).scalars().all()
        counts = dict(
            (await self.db.execute(
                select(BankQuestion.course_id, func.count()).where(BankQuestion.course_id.in_([c.id for c in rows])).group_by(BankQuestion.course_id)
            )).all()
        ) if rows else {}
        return {"items": [{"id": str(c.id), "code": c.code, "name": c.name, "questionCount": counts.get(c.id, 0)} for c in rows]}

    async def list_questions(self, user: AuthenticatedUser, course_id: str, page: int, page_size: int) -> dict:
        course = await self._course(user, course_id)
        total = (await self.db.execute(select(func.count()).select_from(BankQuestion).where(BankQuestion.course_id == course.id))).scalar_one()
        rows = (
            await self.db.execute(
                select(BankQuestion).where(BankQuestion.course_id == course.id)
                .order_by(BankQuestion.created_at.desc(), BankQuestion.id)
                .offset((page - 1) * page_size).limit(page_size)
            )
        ).scalars().all()
        return {
            "total": total, "page": page, "pageSize": page_size,
            "items": [
                {"id": str(q.id), "question": q.question, "options": q.options, "correctIndex": q.correct_index,
                 "explanation": q.explanation, "chapter": q.chapter}
                for q in rows
            ],
        }

    async def delete_question(self, user: AuthenticatedUser, question_id: str, request: Request | None) -> dict:
        try:
            qid = uuid.UUID(question_id)
        except (ValueError, TypeError):
            qid = None
        q = await self.db.get(BankQuestion, qid) if qid else None
        if q is None:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy câu hỏi"})
        course = await self._course(user, str(q.course_id))
        await self.db.delete(q)
        await self.audit.log(
            action="BANK_QUESTION_DELETE", user_id=user.id, entity_type="BankQuestion", entity_id=question_id,
            detail={"course": course.code}, request=request,
        )
        await self.db.commit()
        return {"message": "Đã xóa câu hỏi"}

    # --------------------------------------------------------------- nhập tệp

    @staticmethod
    def _candidates_csv(text: str) -> list[dict]:
        reader = csv.DictReader(io.StringIO(text))
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        missing = [h for h in _REQUIRED if h not in header]
        if missing:
            raise _bad(
                "Thiếu cột: " + ", ".join(missing) + ". Cột hợp lệ: cau_hoi, a, b, c … j, dap_an, giai_thich, chuong",
                "BAD_HEADER",
            )
        out: list[dict] = []
        for line, raw in enumerate(reader, start=2):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            problems: list[str] = []
            opts = [r.get(letter, "") for letter in _LETTERS]
            filled = [i for i, o in enumerate(opts) if o]
            if len(filled) < 2:
                problems.append("cần ít nhất 2 đáp án (cột a, b)")
            elif filled != list(range(len(filled))):
                problems.append("các đáp án phải liền nhau, không bỏ trống giữa chừng")
            options = [opts[i] for i in filled]
            answer = r.get("dap_an", "").lower()
            correct = _LETTERS.index(answer) if len(answer) == 1 and answer in _LETTERS else -1
            if correct < 0 or correct >= len(options):
                problems.append(f"đáp án đúng ({r.get('dap_an') or 'trống'}) phải là một chữ cái ứng với đáp án đã có")
            out.append({"line": line, "question": r.get("cau_hoi", ""), "options": options, "correct": correct,
                        "explanation": r.get("giai_thich", ""), "chapter": r.get("chuong", ""), "problems": problems})
        return out

    @staticmethod
    def _candidates_gift(text: str) -> list[dict]:
        return [
            {"line": g.line, "question": g.question, "options": g.options, "correct": g.correct,
             "explanation": g.explanation, "chapter": g.chapter or "", "problems": list(g.problems)}
            for g in parse_gift(text)
        ]

    async def import_file(
        self, user: AuthenticatedUser, course_id: str, *, content: bytes, filename: str | None, fmt: str,
        dry_run: bool, request: Request | None,
    ) -> dict:
        """Nhập câu hỏi từ tệp GIFT (`fmt="gift"`, mặc định) hoặc CSV (`fmt="csv"`). Dòng lỗi báo theo dòng trong tệp."""
        course = await self._course(user, course_id)
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise _bad("Tệp phải mã hóa UTF-8", "BAD_ENCODING") from exc
        cands = self._candidates_csv(text) if fmt == "csv" else self._candidates_gift(text)
        if len(cands) > IMPORT_MAX_ROWS:
            raise _bad(f"Tối đa {IMPORT_MAX_ROWS} câu mỗi lần", "TOO_MANY_ROWS")
        if not cands:
            raise _bad("Tệp không có câu hỏi nào", "EMPTY_FILE")

        existing = set(
            (await self.db.execute(select(BankQuestion.question_hash).where(BankQuestion.course_id == course.id))).scalars()
        )
        errors: list[dict] = []
        fresh: list[dict] = []
        seen: set[str] = set()
        duplicates = 0
        for c in cands:
            problems = list(c["problems"])
            question, options = c["question"].strip(), [o.strip() for o in c["options"]]
            if not question:
                if "thiếu nội dung câu hỏi" not in problems:
                    problems.append("thiếu nội dung câu hỏi")
            elif len(question) > _LIMITS["cau_hoi"]:
                problems.append(f"câu hỏi dài quá {_LIMITS['cau_hoi']} ký tự")
            if len(options) > MAX_OPTIONS:
                problems.append(f"tối đa {MAX_OPTIONS} đáp án mỗi câu")
            if any(len(o) > _LIMITS["option"] for o in options):
                problems.append(f"có đáp án dài quá {_LIMITS['option']} ký tự")
            if len({o.lower() for o in options}) != len(options):
                problems.append("có hai đáp án giống nhau")
            explanation, chapter = c["explanation"].strip(), c["chapter"].strip()
            if len(explanation) > _LIMITS["giai_thich"]:
                problems.append(f"giải thích dài quá {_LIMITS['giai_thich']} ký tự")
            if len(chapter) > _LIMITS["chuong"]:
                problems.append(f"tên chương dài quá {_LIMITS['chuong']} ký tự")
            if problems:
                errors.append({"line": c["line"], "message": "; ".join(dict.fromkeys(problems))})
                continue
            h = question_hash(question, options)
            if h in existing or h in seen:
                duplicates += 1
                continue
            seen.add(h)
            fresh.append({"question": question, "options": options, "correct": c["correct"], "chapter": chapter or None,
                          "explanation": explanation or f"Đáp án đúng: {options[c['correct']]}.", "hash": h})

        if not errors and len(existing) + len(fresh) > BANK_MAX_PER_COURSE:
            errors.append({"line": 0, "message": f"Ngân hàng của môn tối đa {BANK_MAX_PER_COURSE} câu (hiện có {len(existing)})"})

        # Câu hợp lệ vẫn đếm là `validRows`; chỉ khi KHÔNG còn lỗi mới ghi (tất cả hoặc không gì cả).
        result = {"fileName": filename, "totalRows": len(cands), "validRows": len(fresh) + duplicates, "errors": errors,
                  "dryRun": dry_run, "created": len(fresh), "updated": 0, "unchanged": duplicates, "accepted": False}
        if errors or dry_run:
            result["message"] = (
                f"Phát hiện {len(errors)} câu lỗi, chưa ghi gì" if errors
                else f"Tệp hợp lệ: sẽ thêm {len(fresh)} câu, bỏ qua {duplicates} câu trùng (chạy thử, chưa ghi)"
            )
            return result

        for f in fresh:
            self.db.add(BankQuestion(
                course_id=course.id, created_by_id=uuid.UUID(user.id), question=f["question"], options=f["options"],
                correct_index=f["correct"], explanation=f["explanation"], chapter=f["chapter"], question_hash=f["hash"],
            ))
        await self.audit.log(
            action="BANK_IMPORT", user_id=user.id, entity_type="Course", entity_id=str(course.id),
            detail={"course": course.code, "fileName": filename, "format": fmt, "created": len(fresh), "duplicates": duplicates},
            request=request,
        )
        await self.db.commit()
        result["accepted"] = True
        result["message"] = f"Đã thêm {len(fresh)} câu hỏi vào môn {course.code}, bỏ qua {duplicates} câu trùng"
        return result

    # ------------------------------------------------------------ phía học viên

    async def counts_for_learners(self) -> dict:
        """{courseId: số câu} cho mọi môn đã có ngân hàng — để giao diện ôn tập biết môn nào chọn được nguồn này."""
        rows = (await self.db.execute(select(BankQuestion.course_id, func.count()).group_by(BankQuestion.course_id))).all()
        return {"items": [{"courseId": str(cid), "count": n} for cid, n in rows]}

    async def draw(self, course_id: uuid.UUID, n: int) -> list[BankQuestion]:
        """Rút ngẫu nhiên tối đa `n` câu của môn."""
        return list(
            (await self.db.execute(
                select(BankQuestion).where(BankQuestion.course_id == course_id).order_by(func.random()).limit(n)
            )).scalars()
        )
