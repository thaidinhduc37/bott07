"""Kiểm thử bộ phân tích GIFT (không cần API chạy): python scripts/test/test_gift_parser.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
sys.path.insert(0, str(Path(__file__).parent))
import _http as H  # noqa: E402
from _http import check  # noqa: E402

from app.services.learning.question_gift import parse_gift  # noqa: E402

SAMPLE = r"""// chú thích bị bỏ qua
$CATEGORY: Môn/Chương 1

::Thủ đô:: Thủ đô của Việt Nam là {
=Hà Nội#Đúng rồi
~Huế#Sai
~Đà Nẵng
}

2 + 2 bằng mấy? {~3 =4 ~5 ~6 ~7 ~8 ~9 ~10}

Mã hóa đối xứng dùng {T#Cùng một khóa}

[html]<p>Giao thức nào <b>không</b> mã hóa?</p> {=HTTP ~HTTPS ####Chỉ HTTPS có TLS}

Giá trị \{x\} bằng \~ ký tự nào? {=\= ~\# ~a}

Thủ đô của {=Hà Nội ~Huế} thuộc miền Bắc.

Câu một dòng
nhiều dòng {
~sai 1
=đúng
}

$CATEGORY: $course$/Chương 2/Mạng

Câu có trọng số {~%100%Đúng ~%50%Nửa ~%0%Sai}

Trả lời ngắn {=an =bình}

Ghép cặp {=a -> 1 =b -> 2}

Số học {#3.14}

Tự luận {}

Hai đáp án đúng {=a =b ~c}

Thiếu khối đáp án
"""

qs = parse_gift(SAMPLE)
by = {q.question[:14]: q for q in qs}
check("đếm đủ 14 câu (kể cả câu lỗi)", len(qs) == 14, str(len(qs)))

q = qs[0]
check("trắc nghiệm: 3 đáp án, đúng ở vị trí 0", q.options == ["Hà Nội", "Huế", "Đà Nẵng"] and q.correct == 0 and not q.problems, str(q))
check("chương lấy phần cuối $CATEGORY", q.chapter == "Chương 1", str(q.chapter))
check("tiêu đề :: :: bị bỏ khỏi câu hỏi", q.question == "Thủ đô của Việt Nam là", q.question)
check("lời giải lấy phản hồi của đáp án đúng", q.explanation == "Đúng rồi", q.explanation)
check("số dòng bắt đầu từ dòng sau $CATEGORY", q.line == 4, str(q.line))

q = qs[1]
check("số đáp án tùy ý (8) và đúng ở vị trí 1", len(q.options) == 8 and q.correct == 1 and not q.problems, str(q))

q = qs[2]
check("Đúng/Sai: {T} → Đúng", q.options == ["Đúng", "Sai"] and q.correct == 0 and q.explanation == "Cùng một khóa", str(q))

q = qs[3]
check("[html] bỏ thẻ, phản hồi chung ####", q.question == "Giao thức nào không mã hóa? _____".replace(" _____", "") or q.question.startswith("Giao thức nào không mã hóa?"), q.question)
check("phản hồi chung làm lời giải", q.explanation == "Chỉ HTTPS có TLS" and q.correct == 0, str(q))

q = qs[4]
check("ký tự thoát \{ \} \~ \= \#", q.question == "Giá trị {x} bằng ~ ký tự nào?" and q.options == ["=", "#", "a"] and q.correct == 0, str(q))

q = qs[5]
check("điền chỗ trống ghép _____", q.question == "Thủ đô của _____ thuộc miền Bắc." and q.options == ["Hà Nội", "Huế"] and q.correct == 0, str(q))

q = qs[6]
check("câu nhiều dòng, đáp án xuống dòng", q.question == "Câu một dòng\nnhiều dòng" and q.options == ["sai 1", "đúng"] and q.correct == 1, str(q))

q = qs[7]
check("trọng số 100 là đáp án đúng, chương mới", q.correct == 0 and q.options == ["Đúng", "Nửa", "Sai"] and q.chapter == "Mạng" and not q.problems, str(q))

for i, label in ((8, "trả lời ngắn"), (9, "ghép cặp"), (10, "số"), (11, "tự luận"), (12, "hai đáp án đúng"), (13, "thiếu khối đáp án")):
    check(f"báo lỗi {label}, không đoán", bool(qs[i].problems), str(qs[i]))
check("báo lỗi đúng dòng của câu", qs[13].line == SAMPLE.replace("\r\n", "\n").split("\n").index("Thiếu khối đáp án") + 1, str(qs[13].line))

check("tệp rỗng → không có câu", parse_gift("\n\n// chỉ chú thích\n") == [])
check("CRLF và BOM-less vẫn đúng", len(parse_gift("A {=x ~y}\r\n\r\nB {=x ~y}\r\n")) == 2)

print(f"\n{H.PASSED} đạt, {H.FAILED} lỗi")
sys.exit(1 if H.FAILED else 0)
