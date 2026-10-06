"""Điểm học phần của học viên.

Mỗi dòng = một học viên, một môn, một học kỳ. Các cột điểm thành phần (TH, QT, GK, CK) và điểm học phần
đều có thể trống: học viên đã đăng ký nhưng chưa có điểm thì không có dòng nào (trang kết quả vẫn liệt kê môn
từ lịch học của lớp và hiện dấu "-").

Hệ thống KHÔNG tự suy ra điểm học phần từ các điểm thành phần — trọng số mỗi môn do nhà trường quy định và
chưa có trong dữ liệu — nên điểm học phần là giá trị do giảng viên / phòng đào tạo nhập (thang 10).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import created_at_col, updated_at_col, uuid_pk

# Điểm học phần từ ngưỡng này trở lên là đạt (tích lũy tín chỉ).
PASS_SCORE = 5.0


class CourseGrade(Base):
    __tablename__ = "course_grades"

    id: Mapped[uuid.UUID] = uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        "student_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        "course_id", PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    academic_year: Mapped[str] = mapped_column("academic_year", String, nullable=False)
    semester: Mapped[str] = mapped_column(String, nullable=False)

    practice: Mapped[float | None] = mapped_column(Float, nullable=True)      # TH
    process: Mapped[float | None] = mapped_column(Float, nullable=True)       # QT
    midterm: Mapped[float | None] = mapped_column(Float, nullable=True)       # GK
    final_exam: Mapped[float | None] = mapped_column("final_exam", Float, nullable=True)  # CK
    total: Mapped[float | None] = mapped_column(Float, nullable=True)         # điểm học phần
    note: Mapped[str | None] = mapped_column(String, nullable=True)

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "updated_by_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "academic_year", "semester", name="uq_course_grades_unique"),
        Index("ix_course_grades_student_id", "student_id"),
        Index("ix_course_grades_course_term", "course_id", "academic_year", "semester"),
    )
