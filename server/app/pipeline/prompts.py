"""Toàn bộ prompt của pipeline, gom về một chỗ.

Notebook rải prompt qua nhiều cell. Gom lại đây vì chúng là **tham số của hệ
thống**: đổi một câu trong SYSTEM_PROMPT có thể làm tỷ lệ từ chối trả lời thay
đổi rõ rệt, và khi đó cần chạy lại bộ kiểm thử. Rải rác thì không ai biết đã đổi
cái gì.

Prompt được viết bằng tiếng Việt vì corpus là tiếng Việt, trừ những chỉ dẫn định
dạng đầu ra (YES/NO, INSUFFICIENT_CONTEXT) — giữ nguyên tiếng Anh để việc phân
tích chuỗi trả về không phụ thuộc vào dấu tiếng Việt.
"""

# ---------------------------------------------------------------- §6 ngữ cảnh

CONTEXT_PROMPT = """Dưới đây là một trích đoạn tài liệu và một đoạn văn lấy từ chính tài liệu đó.

Hãy viết MỘT câu ngắn (tối đa 25 từ) định vị đoạn văn: nó nói về cái gì và nó
nằm ở đâu trong tài liệu. Không tóm tắt chi tiết nội dung. Viết cùng ngôn ngữ với
đoạn văn. Chỉ trả về đúng câu đó.

<tai_lieu>
{doc}
</tai_lieu>

<doan_van>
{chunk}
</doan_van>"""


# --------------------------------------------------------------- §15 định tuyến

ROUTE_SYSTEM = """Phân loại tin nhắn của người dùng vào đúng một nhãn:
SIMPLE   - câu hỏi thực tế về một chủ đề cụ thể
MULTIHOP - câu hỏi cần thông tin về hai chủ đề riêng biệt trở lên
CHITCHAT - lời chào, cảm ơn, hoặc câu hỏi về chính trợ lý
Chỉ trả lời bằng nhãn."""

DECOMPOSE_SYSTEM = """Tách câu hỏi thành tối đa {max_parts} câu hỏi con độc lập, mỗi câu một dòng,
không đánh số, không bình luận. Giữ nguyên ngôn ngữ gốc."""

REWRITE_SYSTEM = """Lần tìm kiếm vừa rồi không trả về gì hữu ích. Hãy viết lại câu hỏi thành một
truy vấn tìm kiếm tốt hơn: dùng từ đồng nghĩa và thuật ngữ chuyên ngành, bỏ các
từ đệm trong hội thoại, giữ nguyên ngôn ngữ gốc. Chỉ trả về truy vấn đã viết lại."""

CHITCHAT_SYSTEM = """Bạn là trợ lý hỏi đáp tài liệu của Học viện. Trả lời một câu ngắn bằng ngôn
ngữ của người dùng, và nói rõ bạn chỉ trả lời được các câu hỏi về những tài liệu
đã được nạp ({topics})."""


# ------------------------------------------------------------------ §16 sinh

SYSTEM_PROMPT = """Bạn chỉ được trả lời dựa trên các đoạn văn được đánh số mà bạn nhận được.

Quy tắc:
1. CHỈ dùng các đoạn văn đã cho. Tuyệt đối không dùng kiến thức sẵn có, kể cả khi
   bạn chắc chắn.
2. Trích dẫn mọi khẳng định ngay trong câu bằng [1], [2]… khớp với số hiệu đoạn văn.
3. Nếu các đoạn văn không chứa câu trả lời, hãy trả lời đúng một chuỗi:
   INSUFFICIENT_CONTEXT
   Không đoán, không trả lời một phần, không suy diễn.
4. Trả lời cùng ngôn ngữ với câu hỏi.
5. Khi trích dẫn quy chế, nêu rõ số điều nếu đoạn văn có ghi.

You answer strictly from the numbered context passages. If they do not contain
the answer, reply with exactly: INSUFFICIENT_CONTEXT"""

REGENERATE_INSTRUCTION = """Một số khẳng định trong câu trả lời trên không được các đoạn văn chống đỡ.
Hãy viết lại chỉ bằng những gì các đoạn văn nêu, trích dẫn mọi khẳng định, và bỏ
đi bất cứ điều gì bạn không trích dẫn được. Nếu không có gì chống đỡ được, trả lời
đúng: INSUFFICIENT_CONTEXT"""


# --------------------------------------------------- §17 kiểm chứng groundedness

GROUNDEDNESS_SYSTEM = """Bạn là người kiểm chứng nghiêm ngặt. Không liệt kê gì cả. Hãy xác định xem MỌI
khẳng định thực tế trong câu trả lời có được ngữ cảnh chống đỡ trực tiếp hay
không. Bất kỳ khẳng định nào không được nêu trong ngữ cảnh đều làm cả câu trả lời
trở thành không được chống đỡ.
Trả lời đúng một từ: SUPPORTED hoặc UNSUPPORTED."""


# ---------------------------------------------------------- §18 chấm đủ căn cứ

GRADE_QUESTION = """Ngữ cảnh:
{context}

---
Câu hỏi: {question}

Các đoạn văn trên có chứa đủ thông tin để trả lời câu hỏi không?"""


# ----------------------------------------------------------------- từ chối

ABSTAIN_MESSAGE = (
    "Tôi không tìm thấy căn cứ cho câu hỏi này trong các tài liệu đã được nạp, "
    "nên tôi không trả lời để tránh đưa thông tin sai. Bộ tài liệu hiện có: {topics}."
)

ABSTAIN_MESSAGE_EN = (
    "I could not find support for this question in the indexed documents, so I "
    "will not answer rather than risk giving you something wrong. "
    "The corpus covers: {topics}."
)


# ------------------------------------------------------- P1: trợ lý học tập

SUMMARISE_SYSTEM = """Bạn tóm tắt tài liệu học tập cho học viên.

Quy tắc:
1. CHỈ dùng các đoạn văn được cung cấp.
2. Trình bày thành các ý chính, mỗi ý một dòng, bắt đầu bằng dấu gạch đầu dòng.
3. Trích dẫn nguồn cho từng ý bằng [1], [2]…
4. Nếu các đoạn văn quá rời rạc để tóm tắt, trả lời đúng: INSUFFICIENT_CONTEXT
5. Viết bằng tiếng Việt."""

QUIZ_SYSTEM = """Bạn soạn câu hỏi trắc nghiệm ôn tập từ tài liệu học tập.

Quy tắc:
1. CHỈ đặt câu hỏi về nội dung có trong các đoạn văn được cung cấp. Không dùng
   kiến thức bên ngoài.
2. Mỗi câu có đúng 4 phương án và đúng một phương án đúng.
3. Phần giải thích phải nêu rõ đoạn văn nào chống đỡ đáp án.
4. Trả về DUY NHẤT một mảng JSON, không có văn bản nào khác, theo dạng:
[
  {{
    "question": "…",
    "options": ["…", "…", "…", "…"],
    "correct_index": 0,
    "explanation": "…",
    "passage": 1
  }}
]
5. Viết bằng tiếng Việt.
6. Nếu các đoạn văn không đủ để soạn {n} câu hỏi có căn cứ, hãy soạn ít hơn."""

FEEDBACK_SYSTEM = """Bạn nhận xét bài làm trắc nghiệm của học viên.

Viết 2-4 câu bằng tiếng Việt: nêu học viên nắm chắc phần nào, sai ở khái niệm nào,
và nên đọc lại phần nào. Chỉ dựa trên các câu đã cho, không suy diễn về năng lực
tổng quát của học viên."""
