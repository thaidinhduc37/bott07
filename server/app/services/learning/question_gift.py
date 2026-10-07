"""Phân tích định dạng GIFT của Moodle (câu trắc nghiệm một đáp án đúng, số đáp án tùy ý) thành danh sách câu hỏi.

Hỗ trợ:
  * Trắc nghiệm:   ``::Tiêu đề:: Câu hỏi {=Đáp án đúng ~Sai 1 ~Sai 2}`` (đáp án có thể xuống dòng riêng).
  * Nhiều đáp án đúng: nhiều dấu ``=`` hoặc ``~%50%A ~%50%B ~Sai`` — học viên phải chọn đủ và đúng tất cả.
  * Đúng / Sai:    ``Câu hỏi {T}`` / ``{FALSE}`` → hai lựa chọn "Đúng", "Sai".
  * Phản hồi:      ``#phản hồi`` sau một đáp án; ``####phản hồi chung`` cuối khối → lời giải thích.
  * ``$CATEGORY: a/b/c``   → chương của các câu phía sau (lấy phần cuối).
  * ``~%100%Đáp án``       → đáp án đúng; trọng số khác 100 bị coi là sai.
  * Điền chỗ trống:        ``Thủ đô {=Hà Nội ~Huế} của Việt Nam`` → câu hỏi ghép `_____` vào chỗ trống.
  * Ký tự thoát ``\\~ \\= \\# \\{ \\} \\:``, ``\\n`` là xuống dòng; dòng ``//`` là chú thích; tiền tố ``[html]``,
    ``[markdown]``, ``[plain]``, ``[moodle]`` được bỏ (``[html]`` còn bỏ thẻ).

Không hỗ trợ (báo lỗi ở đúng câu, không bỏ qua im lặng): trả lời ngắn, ghép cặp ``->``, số ``#``, tự luận ``{}``. Các câu hợp lệ vẫn được dùng.

Câu hỏi ngăn cách nhau bằng dòng trống; ``line`` là dòng đầu tiên của câu trong tệp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TF = re.compile(r"^(TRUE|FALSE|T|F)\s*(?:#(.*))?$", re.IGNORECASE | re.DOTALL)
_PREFIX = re.compile(r"^\s*\[(html|markdown|plain|moodle)\]\s*", re.IGNORECASE)
_TITLE = re.compile(r"^\s*::(.*?)::\s*", re.DOTALL)
_WEIGHT = re.compile(r"^%(-?\d+(?:\.\d+)?)%")
_TAGS = re.compile(r"<[^>]+>")


@dataclass
class GiftQuestion:
    line: int
    question: str = ""
    options: list[str] = field(default_factory=list)
    correct: int = -1
    # Mọi chỉ số đáp án đúng (1 phần tử = trắc nghiệm một đáp án đúng, ≥ 2 = nhiều đáp án đúng).
    correct_set: list[int] = field(default_factory=list)
    explanation: str = ""
    chapter: str | None = None
    problems: list[str] = field(default_factory=list)


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), s, flags=re.DOTALL)


def _find_unescaped(s: str, targets: str, start: int = 0) -> int:
    """Vị trí đầu tiên của một ký tự trong `targets` không bị `\\` thoát; -1 nếu không có."""
    i = start
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] in targets:
            return i
        i += 1
    return -1


def _split_answers(inner: str) -> tuple[str, list[tuple[str, str]]]:
    """Tách phần trước dấu đáp án đầu tiên và danh sách (dấu `=`/`~`, nội dung)."""
    first = _find_unescaped(inner, "=~")
    if first < 0:
        return inner, []
    head, rest = inner[:first], inner[first:]
    parts: list[tuple[str, str]] = []
    i = 0
    while i < len(rest):
        marker = rest[i]
        nxt = _find_unescaped(rest, "=~", i + 1)
        end = len(rest) if nxt < 0 else nxt
        parts.append((marker, rest[i + 1 : end]))
        i = end
    return head, parts


def _answer(raw: str) -> tuple[str, str, float | None]:
    """(nội dung, phản hồi, trọng số) của một đáp án."""
    raw = raw.strip()
    weight = None
    m = _WEIGHT.match(raw)
    if m:
        weight = float(m.group(1))
        raw = raw[m.end() :].strip()
    cut = _find_unescaped(raw, "#")
    text, feedback = (raw, "") if cut < 0 else (raw[:cut], raw[cut + 1 :])
    return _unescape(text.strip()), _unescape(feedback.strip()), weight


def _parse_block(text: str, line: int, chapter: str | None) -> GiftQuestion:
    q = GiftQuestion(line=line, chapter=chapter)
    title = _TITLE.match(text)
    if title:
        text = text[title.end() :]

    open_ = _find_unescaped(text, "{")
    close = _find_unescaped(text, "}", open_ + 1) if open_ >= 0 else -1
    if open_ < 0 or close < 0:
        q.problems.append("không có khối đáp án { … }")
        return q
    before, after, inner = text[:open_], text[close + 1 :], text[open_ + 1 : close]

    stem = before.strip() + (" _____ " + after.strip() if after.strip() else "")
    prefix = _PREFIX.match(stem)
    if prefix:
        stem = stem[prefix.end() :]
        if prefix.group(1).lower() == "html":
            stem = _TAGS.sub("", stem)
    q.question = _unescape(stem.strip())
    if not q.question:
        q.problems.append("thiếu nội dung câu hỏi")

    general = ""
    cut = inner.find("####")
    if cut >= 0 and _find_unescaped(inner, "#") <= cut:
        inner, general = inner[:cut], inner[cut + 4 :]
    inner = inner.strip()

    tf = _TF.match(inner)
    if tf:
        q.options = ["Đúng", "Sai"]
        q.correct = 0 if tf.group(1).upper().startswith("T") else 1
        q.correct_set = [q.correct]
        q.explanation = _unescape((general or tf.group(2) or "").strip())
        return q

    if not inner:
        q.problems.append("câu tự luận (khối đáp án trống) chưa được hỗ trợ")
        return q
    if inner.startswith("#"):
        q.problems.append("câu trả lời dạng số chưa được hỗ trợ")
        return q
    head, parts = _split_answers(inner)
    if head.strip():
        q.problems.append("khối đáp án có nội dung trước dấu = hoặc ~ (dạng câu hỏi chưa được hỗ trợ)")
        return q
    if not parts:
        q.problems.append("khối đáp án không có đáp án nào (cần = cho đáp án đúng, ~ cho đáp án sai)")
        return q
    if all(marker == "=" for marker, _ in parts):
        q.problems.append("câu trả lời ngắn (chỉ có dấu =) chưa được hỗ trợ — cần thêm đáp án sai bằng ~")
        return q

    correct: list[int] = []
    feedback = ""
    for marker, raw in parts:
        text_, fb, weight = _answer(raw)
        if "->" in text_:
            q.problems.append("câu ghép cặp (->) chưa được hỗ trợ")
            return q
        if not text_:
            q.problems.append("có đáp án trống")
        # `=` luôn là đúng; `~%w%` với w > 0 là đúng (Moodle: nhiều đáp án đúng chia điểm, vd ~%50%A ~%50%B).
        if marker == "=" or (weight is not None and weight > 0):
            correct.append(len(q.options))
            feedback = feedback or fb
        q.options.append(text_)
    if not correct:
        q.problems.append("chưa có đáp án đúng (đánh dấu bằng = hoặc ~%100%)")
    elif len(correct) == len(q.options):
        q.problems.append("mọi đáp án đều đúng — cần ít nhất một đáp án sai")
    else:
        q.correct = correct[0]
        q.correct_set = correct
    q.explanation = _unescape(general.strip()) or feedback
    return q


def parse_gift(text: str) -> list[GiftQuestion]:
    """Phân tích cả tệp; câu lỗi vẫn có mặt (kèm `problems`) để báo đúng dòng."""
    out: list[GiftQuestion] = []
    chapter: str | None = None
    block: list[str] = []
    start = 0

    def flush() -> None:
        nonlocal block, chapter
        if not block:
            return
        lines, first = block, start
        block = []
        if lines[0].strip().upper().startswith("$CATEGORY:"):
            value = lines[0].split(":", 1)[1].strip().rstrip("/")
            chapter = value.split("/")[-1].strip() or None
            lines, first = lines[1:], start + 1
            if not lines:
                return
        out.append(_parse_block("\n".join(lines), first, chapter))

    for number, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        stripped = raw.strip()
        if stripped.startswith("//"):
            continue
        if not stripped:
            flush()
            continue
        if not block:
            start = number
        block.append(raw)
    flush()
    return out
