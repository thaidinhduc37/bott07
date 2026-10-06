"""§18 Điều phối — vòng lặp truy xuất, chấm, viết lại.

Các stage phía trên được ghép thành một **máy trạng thái**, không phải một đường
thẳng. Pipeline một lượt đặt trần độ chính xác của nó ngay ở truy xuất tầng một:
nếu cách diễn đạt ban đầu trượt thì không gì phía sau cứu được. Cho hệ thống tự
nhận ra bằng chứng của nó không đủ rồi thử một truy vấn khác là thứ biến một
pipeline cố định thành một thứ có thể tự sửa.

Mỗi lần chạy trả về một **trace** các trạng thái đã đi qua. Trace không phải log
gỡ lỗi thừa: nó là bằng chứng về *cách* câu trả lời được tạo ra, và không có nó
thì không kiểm chứng được rằng cổng abstention thực sự đã chạy.

    định tuyến ──chitchat──────────────────────────────► trả lời trực tiếp
       │ simple / multihop
       ▼
    phân rã (chỉ với multihop)
       ▼
    ┌► truy xuất ──► độ tin cậy < τ ? ──có──► TỪ CHỐI
    │      │ không
    │      ▼
    │   chấm bằng chứng ──không đủ──► viết lại ──┐
    │                                            │  (tối đa MAX_RETRIEVAL_ROUNDS)
    └────────────────────────────────────────────┘
           │ đủ
           ▼
        sinh câu trả lời ──► kiểm chứng ──không chống đỡ──► sinh lại ──► vẫn hỏng ──► TỪ CHỐI
                                 │ được chống đỡ
                                 ▼
                          câu trả lời + trích dẫn
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from app.pipeline import blocking, prompts
from app.pipeline.llm import BaseReader, LlmUnavailable
from app.pipeline.retrieval import Hit, Retriever

log = logging.getLogger("rag.orchestrator")

CITE_RE = re.compile(r"\[(\d+)\]")

# Số ký tự tối đa của mỗi đoạn văn đưa vào bước chấm đủ căn cứ (một chunk thường
# dài 1000-1600 ký tự).
GRADE_CHARS_PER_HIT = 1800

# Mật độ dấu tiếng Việt, dùng để chọn ngôn ngữ của lời từ chối. Được huấn luyện
# trên chuỗi năm-mười từ như câu hỏi thực tế thì đáng tin hơn các bộ nhận diện
# ngôn ngữ thống kê (vd. `langdetect`), vốn cần văn bản dài hơn để ổn định.
_VN_CHARS = re.compile(
    r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
    r"òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]"
)


def is_vietnamese(text: str) -> bool:
    low = text.lower()
    if not _VN_CHARS.search(low):
        return False
    return len(_VN_CHARS.findall(low)) / max(len(low), 1) > 0.01


@dataclass
class RagResult:
    question: str
    answer: str = ""
    hits: list[Hit] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    abstained: bool = False
    abstain_reason: str | None = None
    grounded: bool | None = None
    confidence: float = 0.0
    threshold: float = 0.0
    rounds: int = 0
    route: str = "SIMPLE"
    trace: list[str] = field(default_factory=list)
    latency_ms: int = 0
    llm_calls: int = 0


def cited_markers(answer: str, n_passages: int) -> list[int]:
    return sorted({int(m) for m in CITE_RE.findall(answer) if 1 <= int(m) <= n_passages})


def build_context(hits: list[Hit]) -> str:
    """Ngữ cảnh đánh số đưa cho reader.

    Mỗi đoạn mang nhãn nguồn thật. Vì việc đánh số được chống lưng bởi siêu dữ
    liệu có thật, một trích dẫn [n] giải được về một vị trí mà con người mở ra
    kiểm tra được — đó chính là khác biệt giữa một trích dẫn và vẻ ngoài của nó.
    """
    parts = []
    for i, h in enumerate(hits, start=1):
        p = h.payload
        locator = f"trang {p.get('page')}" if p.get("page") else ""
        if p.get("article_number"):
            locator = f"{p['article_number']}" + (f", {locator}" if locator else "")
        head = f"[{i}] (nguồn: {p.get('source', '')}" + (f", {locator}" if locator else "") + ")"
        parts.append(f"{head}\n{h.text}")
    return "\n\n".join(parts)


class Orchestrator:
    def __init__(self, retriever: Retriever, reader: BaseReader, settings):
        self.retriever = retriever
        self.reader = reader
        self.settings = settings

    # ------------------------------------------------------------ §15 truy vấn

    async def route(self, question: str) -> str:
        raw = (
            await self.reader.chat(
                question, system=prompts.ROUTE_SYSTEM, max_output_tokens=8, tag="route"
            )
        ).upper()
        for label in ("MULTIHOP", "CHITCHAT", "SIMPLE"):
            if label in raw:
                return label
        return "SIMPLE"

    async def decompose(self, question: str) -> list[str]:
        raw = await self.reader.chat(
            question,
            system=prompts.DECOMPOSE_SYSTEM.format(max_parts=self.settings.max_subqueries),
            max_output_tokens=200,
            tag="decompose",
        )
        parts = [l.strip(" -•\t") for l in raw.split("\n") if len(l.strip()) > 8]
        return parts[: self.settings.max_subqueries] or [question]

    async def rewrite(self, question: str, attempted: list[str]) -> str:
        raw = await self.reader.chat(
            f"Câu hỏi: {question}\nĐã thử: {'; '.join(attempted)}",
            system=prompts.REWRITE_SYSTEM,
            max_output_tokens=100,
            tag="rewrite",
        )
        return raw.split("\n")[0].strip().strip('"') or question

    # -------------------------------------------------- §18 chấm bằng chứng

    async def grade_sufficiency(self, question: str, hits: list[Hit]) -> bool:
        # Chấm trên cùng bộ đoạn văn mà bước sinh sẽ đọc, không cắt cụt. Trước đây
        # chỉ lấy 3 đoạn đầu, mỗi đoạn 900 ký tự: đoạn chứa đáp án nằm ở hạng 1
        # nhưng câu "Một tín chỉ bằng 15 giờ giảng… kèm 30 giờ tự học" bị cắt ngang
        # nên bước chấm kết luận "thiếu" và hệ thống từ chối một câu hỏi có đáp án.
        ctx = "\n\n".join(h.text[:GRADE_CHARS_PER_HIT] for h in hits)
        verdict = await self.reader.yes_no(
            prompts.GRADE_QUESTION.format(context=ctx, question=question), tag="grade"
        )
        # `None` (không phân tích được) được coi là ĐỦ, không phải thiếu: lỗi
        # phân tích không được biến thành lời từ chối. Cổng τ và bước kiểm chứng
        # groundedness vẫn đứng phía sau.
        return verdict is not False

    # ----------------------------------------------- §17 kiểm chứng groundedness

    async def check_grounded(self, answer: str, context: str) -> bool | None:
        if answer.strip().startswith("INSUFFICIENT_CONTEXT"):
            return True
        raw = (
            await self.reader.chat(
                f"Ngữ cảnh:\n{context}\n\n---\nCâu trả lời:\n{answer}",
                system=prompts.GROUNDEDNESS_SYSTEM,
                max_output_tokens=8,
                tag="groundedness",
            )
        ).upper()
        if "UNSUPPORTED" in raw:
            return False
        if "SUPPORTED" in raw:
            return True
        return None

    # ------------------------------------------------------------- §16 sinh

    async def generate(self, question: str, hits: list[Hit], extra: str | None = None) -> str:
        context = build_context(hits)
        prompt = f"Ngữ cảnh:\n{context}\n\n---\nCâu hỏi: {question}"
        if extra:
            prompt += f"\n\n---\n{extra}"
        return await self.reader.chat(
            prompt, system=prompts.SYSTEM_PROMPT, max_output_tokens=1024, tag="generate"
        )

    # ---------------------------------------------------------------- từ chối

    def abstain_text(self, question: str, topics: str) -> str:
        template = (
            prompts.ABSTAIN_MESSAGE if is_vietnamese(question) else prompts.ABSTAIN_MESSAGE_EN
        )
        return template.format(topics=topics or "chưa có tài liệu nào được nạp")

    # ------------------------------------------------------------------ chạy

    async def answer(
        self,
        question: str,
        collection: str,
        *,
        topics: str = "",
        course_id: str | None = None,
        top_k: int | None = None,
        tau: float | None = None,
        use_router: bool = True,
    ) -> RagResult:
        tau = self.settings.answer_threshold if tau is None else tau
        top_k = top_k or self.settings.final_k
        t0 = time.time()
        calls_before = sum(self.reader.usage.calls.values())

        res = RagResult(question=question, threshold=tau)
        log_step = res.trace.append

        def finish() -> RagResult:
            res.latency_ms = int((time.time() - t0) * 1000)
            res.llm_calls = sum(self.reader.usage.calls.values()) - calls_before
            # Ghi nhà cung cấp thật sự đã phục vụ truy vấn này. Với chuỗi dự
            # phòng, việc chuyển làn giữa chừng là thay đổi *có thể quan sát*
            # đối với câu trả lời — model khác thì cách diễn đạt khác — nên nó
            # phải nằm trong trace chứ không chỉ trong log của máy chủ.
            if res.llm_calls:
                provider = getattr(self.reader, "last_provider", "") or self.reader.provider
                model = getattr(self.reader, "last_model", "") or self.reader.model
                res.trace.append(f"llm={provider}:{model}")
            return res

        # --- định tuyến -------------------------------------------------------
        try:
            res.route = await self.route(question) if use_router else "SIMPLE"
        except LlmUnavailable:
            # Không có LLM thì vẫn truy xuất được; chỉ là không định tuyến được.
            # Đây là hạ cấp có kiểm soát, không phải sập.
            res.route = "SIMPLE"
            log_step("route=UNAVAILABLE->SIMPLE")
        else:
            log_step(f"route={res.route}")

        if res.route == "CHITCHAT":
            try:
                res.answer = await self.reader.chat(
                    question,
                    system=prompts.CHITCHAT_SYSTEM.format(topics=topics or "chưa có tài liệu nào"),
                    max_output_tokens=150,
                    tag="chitchat",
                )
            except LlmUnavailable as e:
                res.answer = ""
                res.abstained = True
                res.abstain_reason = str(e)
            log_step("direct_reply")
            return finish()

        # --- phân rã ---------------------------------------------------------
        queries = [question]
        if res.route == "MULTIHOP":
            try:
                queries = await self.decompose(question)
                if len(queries) > 1:
                    log_step(f"decomposed->{len(queries)}")
            except LlmUnavailable:
                log_step("decompose=UNAVAILABLE")

        # --- vòng lặp truy xuất → chấm → viết lại ----------------------------
        attempted: list[str] = []
        hits: list[Hit] = []
        sufficient = False

        # Vòng tốt nhất, không phải vòng cuối.
        #
        # Viết lại truy vấn là một phỏng đoán, và phỏng đoán thì có lúc sai. Quan
        # sát được trên câu "Sinh viên bị cảnh báo học tập trong trường hợp nào?":
        # vòng 1 đạt conf 0.361 — gấp mười hai lần τ — rồi bản viết lại tụt xuống
        # 0.006, và hệ thống báo "độ tin cậy dưới ngưỡng".
        #
        # Câu đó nói dối. Truy xuất tốt nhất KHÔNG dưới ngưỡng; chỉ có lần đoán
        # cuối cùng là dưới. Giữ vòng cuối biến một bản viết lại tồi thành lời
        # kết tội nhắm vào tầng truy xuất, và người vận hành đọc thông báo đó sẽ
        # đi chỉnh sai chỗ.
        #
        # Giữ vòng tốt nhất cũng là điều vòng lặp vốn đang cố đạt được: nó viết
        # lại để tìm bằng chứng *tốt hơn*, nên khi không tốt hơn thì kết quả đúng
        # là cái tốt nhất đã tìm được, không phải cái tìm sau cùng.
        best_hits: list[Hit] = []
        best_conf = -1.0
        best_round = 0

        for rnd in range(1, self.settings.max_retrieval_rounds + 1):
            res.rounds = rnd

            candidates: list[dict] = []
            seen: set[tuple] = set()
            for q in queries:
                # Nhúng truy vấn chiếm CPU, nên đi qua luồng worker: event loop
                # phải còn phục vụ được /health trong lúc truy xuất chạy.
                for payload in await blocking.run(
                    self.retriever.candidates,
                    q,
                    collection,
                    self.settings.candidates_k,
                    course_id,
                ):
                    key = (payload.get("document_id"), payload.get("chunk_id"))
                    if key not in seen:
                        seen.add(key)
                        candidates.append(payload)

            # Xếp lại hạng luôn dùng câu hỏi GỐC, kể cả khi truy xuất dùng bản
            # viết lại: bản viết lại là công cụ tìm kiếm, còn thứ cần chấm là
            # đoạn văn có trả lời được điều người dùng thực sự hỏi hay không.
            hits = await blocking.run(self.retriever.rerank, question, candidates, top_k)
            res.confidence = self.retriever.confidence(hits)
            log_step(f"round{rnd}:retrieved={len(hits)},conf={res.confidence:.3f}")

            if res.confidence > best_conf:
                best_conf, best_hits, best_round = res.confidence, hits, rnd

            # --- LỚP 1: cổng abstention đã calibrate (§14) --------------------
            # Đây không phải quyết định sinh văn bản, nên không thể bị một câu
            # hỏi khéo léo thuyết phục để bỏ qua.
            if res.confidence < tau:
                log_step("gate=below_threshold")
            else:
                # --- LỚP 2: chấm bằng chứng (§18) ----------------------------
                try:
                    sufficient = await self.grade_sufficiency(question, hits)
                except LlmUnavailable:
                    sufficient = True
                    log_step("grade=UNAVAILABLE->assume_sufficient")
                else:
                    log_step("grade=sufficient" if sufficient else "grade=insufficient")
                if sufficient:
                    break

            if rnd < self.settings.max_retrieval_rounds:
                attempted.extend(queries)
                try:
                    rewritten = await self.rewrite(question, attempted)
                    queries = [rewritten]
                    log_step(f"rewrite->{rewritten[:60]}")
                except LlmUnavailable:
                    log_step("rewrite=UNAVAILABLE")
                    break

        # Ra khỏi vòng lặp mà chưa đủ căn cứ nghĩa là mọi bản viết lại đều thất
        # bại. Khi đó báo cáo vòng tốt nhất: nó vừa là chẩn đoán trung thực, vừa
        # là bộ đoạn văn hữu ích nhất để người dùng tự đối chiếu.
        if not sufficient and best_round != res.rounds:
            hits = best_hits
            res.confidence = best_conf
            log_step(f"fallback->round{best_round}:conf={best_conf:.3f}")

        res.hits = hits

        if res.confidence < tau or not sufficient:
            res.abstained = True
            res.abstain_reason = (
                f"Độ tin cậy truy xuất {res.confidence:.3f} dưới ngưỡng {tau:.3f}"
                if res.confidence < tau
                else "Các đoạn văn truy xuất được không chứa đủ căn cứ"
            )
            res.answer = self.abstain_text(question, topics)
            log_step("ABSTAIN")
            return finish()

        # --- sinh câu trả lời -------------------------------------------------
        context = build_context(hits)
        try:
            answer = await self.generate(question, hits)
        except LlmUnavailable as e:
            res.abstained = True
            res.abstain_reason = str(e)
            res.answer = ""
            log_step("generate=UNAVAILABLE")
            return finish()
        log_step("generated")

        if answer.strip().startswith("INSUFFICIENT_CONTEXT"):
            res.abstained = True
            res.abstain_reason = "Mô hình xác định các đoạn văn không chứa câu trả lời"
            res.answer = self.abstain_text(question, topics)
            log_step("reader_declined->ABSTAIN")
            return finish()

        # --- LỚP 3: kiểm chứng groundedness (§17) ----------------------------
        try:
            res.grounded = await self.check_grounded(answer, context)
        except LlmUnavailable:
            res.grounded = None
            log_step("groundedness=UNAVAILABLE")
        else:
            log_step(f"grounded={res.grounded}")

        if res.grounded is False:
            try:
                answer = await self.generate(question, hits, extra=prompts.REGENERATE_INSTRUCTION)
                res.grounded = await self.check_grounded(answer, context)
                log_step(f"regenerated,grounded={res.grounded}")
            except LlmUnavailable:
                log_step("regenerate=UNAVAILABLE")

            if answer.strip().startswith("INSUFFICIENT_CONTEXT") or res.grounded is False:
                res.abstained = True
                res.abstain_reason = "Câu trả lời không được các đoạn văn chống đỡ sau khi sinh lại"
                res.answer = self.abstain_text(question, topics)
                log_step("ABSTAIN_after_verification")
                return finish()

        res.answer = answer
        markers = cited_markers(answer, len(hits))
        res.citations = [hits[m - 1].citation(m) for m in markers]
        return finish()
