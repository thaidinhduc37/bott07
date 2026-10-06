"""Nạp lịch học / lịch thi từ CSV (kiểm tra từng dòng, xung đột trong tệp và với CSDL, upsert theo external_id)."""


from __future__ import annotations


from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import Course, ExamSchedule, Schedule, StudyClass
from app.services.academic.schedule_csv import detect_conflicts, parse_exam_csv, parse_schedule_csv, sniff_is_exam


class ImportMixin:
    async def import_schedules(
        self, *, file_bytes: bytes, filename: str | None, class_id: str, dry_run: bool, allow_partial: bool,
        user: AuthenticatedUser, request: Request | None,
    ) -> dict:
        study_class = await self.db.get(StudyClass, class_id)
        if not study_class:
            raise HTTPException(status_code=400, detail={"message": "Không tìm thấy lớp học"})

        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail={"message": "File CSV phải là UTF-8"})

        is_exam = sniff_is_exam(filename, text)
        parsed = parse_exam_csv(text) if is_exam else parse_schedule_csv(text)

        errors: list[dict] = [
            {"line": e.line, "column": e.column, "message": e.message} for e in parsed.errors
        ]
        total_rows = len(parsed.rows) + len({e.line for e in parsed.errors} - {r["_line"] for r in parsed.rows})
        conflicts: list[dict] = []

        def result(*, accepted: bool, imported: int, created: int | None, updated: int | None,
                   importable: int, new_courses: list[str], message: str) -> dict:
            """Khuôn kết quả đúng kiểu `ImportResult` phía client (trang Nạp lịch).
            Giữ thêm các khóa cũ (`success`, `isExam`, `wouldImport`) cho tương thích."""
            return {
                "fileName": filename or "",
                "class": study_class.code,
                **({"kind": "exam"} if is_exam else {}),
                "totalRows": total_rows,
                "validRows": importable,
                "errors": errors,
                "conflicts": conflicts,
                "dryRun": dry_run,
                "accepted": accepted,
                "imported": imported,
                "created": created,
                "updated": updated,
                "newCourses": new_courses,
                "message": message,
                "success": accepted,
                "isExam": is_exam,
                **({"wouldImport": importable} if dry_run else {}),
            }

        # Row-level: class_code in the file must match the target class
        # (single-class-per-import assumption, matching the demo's 1-class
        # scope) — mismatches are additional row errors, not silently ignored.
        valid_rows = []
        for row in parsed.rows:
            if row["class_code"] != study_class.code:
                errors.append({
                    "line": row["_line"], "column": "class_code",
                    "message": f'class_code "{row["class_code"]}" không khớp lớp đang nhập ("{study_class.code}")',
                })
                continue
            valid_rows.append(row)

        within_file_conflicts = detect_conflicts(valid_rows)
        for c in within_file_conflicts:
            errors.append({"line": c["lineB"], "column": "schedule", "message": f'{c["reason"]} (dòng {c["lineA"]})'})
            conflicts.append({
                "a": f'dòng {c["lineA"]}', "b": f'dòng {c["lineB"]}',
                "kind": "ROOM" if c["reason"].startswith("Trùng phòng")
                else "CLASS" if c["reason"] == "Trùng lịch của lớp" else "INSTRUCTOR",
                "message": c["reason"],
            })

        existing_external_ids = {r["external_id"] for r in valid_rows}
        model = ExamSchedule if is_exam else Schedule
        db_conflicts = await self._db_conflicts_for_import(model, valid_rows, existing_external_ids)
        for dc in db_conflicts:
            errors.append(dc)

        noun = "lịch thi" if is_exam else "lịch học"
        known_codes = {c for (c,) in (await self.db.execute(select(Course.code))).all()}
        new_courses = sorted({r["course_code"] for r in valid_rows} - known_codes)

        if errors and not allow_partial:
            return result(
                accepted=False, imported=0, created=0, updated=0,
                importable=len({r["_line"] for r in valid_rows} - {e["line"] for e in errors}),
                new_courses=[],
                message=f"Tệp {noun} có {len(errors)} lỗi nên chưa nạp gì. Sửa các dòng lỗi rồi nạp lại, "
                        "hoặc bật tùy chọn nạp các dòng hợp lệ.",
            )

        # Rows whose line number matches an error are skipped even under
        # allow_partial — only genuinely valid rows get written.
        error_lines = {e["line"] for e in errors}
        importable = [r for r in valid_rows if r["_line"] not in error_lines]

        if dry_run:
            return result(
                accepted=True, imported=0, created=None, updated=None, importable=len(importable),
                new_courses=new_courses,
                message=f"Kiểm tra thử: {len(importable)}/{total_rows} dòng {noun} hợp lệ, chưa ghi gì vào hệ thống.",
            )

        created, updated = await self._upsert_rows(model, importable, class_id=str(study_class.id))

        if created or updated:
            await self._notify_class(
                str(study_class.id),
                f'Đã cập nhật {noun}: {created} buổi mới, {updated} buổi thay đổi.',
                None,
            )

        await self.audit.log(
            action="SCHEDULE_IMPORT", user_id=user.id, entity_type="StudyClass", entity_id=str(study_class.id),
            detail={"isExam": is_exam, "created": created, "updated": updated, "errorCount": len(errors)},
            request=request,
        )
        await self.db.commit()

        return result(
            accepted=True, imported=created + updated, created=created, updated=updated,
            importable=len(importable), new_courses=new_courses,
            message=f"Đã nạp {created + updated} dòng {noun} ({created} mới, {updated} cập nhật)"
                    + (f"; bỏ qua {len(errors)} dòng lỗi." if errors else "."),
        )

    async def _db_conflicts_for_import(self, model, rows: list[dict], own_external_ids: set[str]) -> list[dict]:
        """Against-DB conflict check, excluding DB rows that are about to be
        overwritten by one of THIS file's own external_ids (a re-import
        updating its own row is not a conflict with itself)."""
        conflicts: list[dict] = []
        if not rows:
            return conflicts
        # Only bother querying the DB window actually touched by this batch.
        min_start = min(r["starts_at"] for r in rows)
        max_end = max(r["ends_at"] for r in rows)
        stmt = select(model).where(model.starts_at < max_end, model.ends_at > min_start)
        db_rows = (await self.db.execute(stmt)).scalars().all()
        db_rows = [d for d in db_rows if d.external_id not in own_external_ids]
        if not db_rows:
            return conflicts

        for r in rows:
            for d in db_rows:
                if r["starts_at"] < d.ends_at and r["ends_at"] > d.starts_at and r["room"] == d.room:
                    conflicts.append({
                        "line": r["_line"], "column": "room",
                        "message": f'Trùng phòng "{r["room"]}" với lịch đã có trong hệ thống ({d.external_id})',
                    })
        return conflicts

    async def _upsert_rows(self, model, rows: list[dict], *, class_id: str) -> tuple[int, int]:
        created = 0
        updated = 0
        for row in rows:
            course = (await self.db.execute(select(Course).where(Course.code == row["course_code"]))).scalar_one_or_none()
            if not course:
                course = Course(code=row["course_code"], name=row["course_name"], credits=row["credits"] or 0)
                self.db.add(course)
                await self.db.flush()

            existing = (
                await self.db.execute(
                    select(model).where(
                        model.academic_year == row["academic_year"], model.semester == row["semester"],
                        model.external_id == row["external_id"],
                    )
                )
            ).scalar_one_or_none()

            common = dict(
                external_id=row["external_id"], academic_year=row["academic_year"], semester=row["semester"],
                class_id=class_id, course_id=course.id, starts_at=row["starts_at"], ends_at=row["ends_at"],
                room=row["room"], building=row["building"], status=row["status"], note=row["note"],
            )
            if model is Schedule:
                common.update(
                    session_date=row["session_date"], week_number=row["week_number"],
                    start_period=row["start_period"], end_period=row["end_period"],
                    instructor=row["instructor"], delivery_mode=row["delivery_mode"], session_type=row["session_type"],
                )
            else:
                common.update(
                    exam_date=row["exam_date"], shift=row["shift"], duration_minutes=row["duration_minutes"],
                    exam_format=row["exam_format"], exam_format_raw=row["exam_format_raw"],
                    allowed_materials=row["allowed_materials"], candidate_count=row["candidate_count"],
                    chief_proctor=row["chief_proctor"], second_proctor=row["second_proctor"],
                )

            if existing is None:
                self.db.add(model(**common))
                created += 1
            else:
                for k, v in common.items():
                    if k in ("external_id", "academic_year", "semester"):
                        continue
                    setattr(existing, k, v)
                updated += 1
        await self.db.flush()
        return created, updated
