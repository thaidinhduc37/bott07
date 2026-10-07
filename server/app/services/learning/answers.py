"""Đáp án của câu trắc nghiệm một hoặc nhiều đáp án đúng, dùng chung cho bài làm, sổ câu sai, sổ tay và thống kê.

Câu một đáp án đúng chỉ có `correct_index`; câu nhiều đáp án đúng có thêm `correct_set` (danh sách chỉ số, ≥ 2 phần tử).
`correct_index` luôn có giá trị (phần tử nhỏ nhất của tập đúng) để chỗ đọc cũ không vỡ.
"""

from __future__ import annotations

LETTERS = "ABCDEFGHIJ"


def correct_of(obj) -> list[int]:
    """Các chỉ số đáp án đúng, sắp xếp tăng dần."""
    return sorted(obj.correct_set) if obj.correct_set else [obj.correct_index]


def selected_of(obj) -> list[int]:
    """Các chỉ số học viên đã chọn (rỗng nếu bỏ trống)."""
    if getattr(obj, "selected_set", None):
        return sorted(obj.selected_set)
    return [obj.selected_index] if obj.selected_index is not None else []


def correct_text(options: list[str], indexes: list[int]) -> str:
    """"A. Hà Nội" hoặc "A, C. Hà Nội; Đà Nẵng" — chữ cái đứng trước, nội dung các đáp án đứng sau."""
    letters = ", ".join(LETTERS[i] for i in indexes)
    return f"{letters}. " + "; ".join(options[i] for i in indexes)
