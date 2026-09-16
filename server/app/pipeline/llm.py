"""Reader — bản thay thế cho Qwen2.5-7B cục bộ của notebook.

Notebook dùng một model duy nhất cho *mọi* stage cần sinh văn bản: viết ngữ cảnh
cho chunk (§6), sinh bộ câu hỏi đánh giá (§12), định tuyến và phân rã truy vấn
(§15), chấm đủ căn cứ (§18), sinh câu trả lời (§16), và kiểm chứng groundedness
(§17). Module này giữ nguyên cấu trúc đó, chỉ đổi chỗ thực thi: máy demo không có
GPU nên chạy 7B cục bộ là không khả thi.

Ba điều được giữ nguyên từ notebook vì chúng ảnh hưởng tới kết quả:

1. **Sinh văn bản là greedy** (`temperature=0`). Với hệ thống có căn cứ, khả năng
   lặp lại quan trọng hơn sự đa dạng; giải mã ngẫu nhiên làm mọi số đo bên dưới
   không lặp lại được.
2. **Đếm số lời gọi theo từng stage.** Notebook có `LLM_CALLS = Counter()` để
   biết mỗi stage tốn bao nhiêu lần sinh. Ở đây nó còn quan trọng hơn vì mỗi lời
   gọi là tiền và là quota.
3. **`yes_no` trả về `None` khi không phân tích được.** Ép một câu trả lời không
   rõ ràng thành `False` sẽ âm thầm biến lỗi phân tích thành "không đủ căn cứ".

--------------------------------------------------------------------------------
Cấu trúc: một lớp cơ sở, hai nhà cung cấp, một chuỗi dự phòng
--------------------------------------------------------------------------------

`BaseReader` giữ toàn bộ phần khó: cầu dao, lùi-thử-lại theo `retryDelay` của nhà
cung cấp, phân biệt hết-hạn-mức với bị-chặn-tốc-độ, đếm lời gọi theo stage, và
ngân sách token nới cho model có thinking. Nhà cung cấp chỉ phải cài đúng một
hàm `_generate()`.

Điều đó quan trọng vì phần dễ sai không nằm ở lời gọi HTTP mà ở cách xử lý lỗi.
Viết lại nó cho mỗi nhà cung cấp là cách chắc chắn để hai đường đi hành xử khác
nhau dưới áp lực — và áp lực chính là lúc ta cần chúng giống nhau.

`ChainReader` nối nhiều reader lại: khi cầu dao của cái đầu mở, nó chuyển sang
cái sau và **ghi lại việc chuyển làn**. Hết hạn mức khi đó không còn là mất chức
năng mà là một sự kiện nhìn thấy được.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field

log = logging.getLogger("rag.llm")


class LlmUnavailable(RuntimeError):
    """Không gọi được LLM. Bên gọi phải báo lỗi rõ ràng, không được im lặng."""


# "retryDelay": "37s" trong phần chi tiết lỗi của Google API.
_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)s")

# Dấu hiệu hết hạn mức hẳn, khác với bị chặn tốc độ trong một cửa sổ ngắn.
#
# Bốn dấu hiệu đầu là của Google. Ba dấu hiệu cuối là của Hugging Face Inference
# Providers: tài khoản miễn phí có định mức tín dụng theo tháng, và khi cạn thì
# router trả 402 kèm "exceeded your monthly included credits" — không phải 429.
# Coi nó là chặn tốc độ sẽ khiến hệ thống ngồi thử lại cho tới đầu tháng sau.
_HARD_QUOTA_MARKERS = (
    "exceeded your current quota",
    "check your plan and billing",
    "billing details",
    "quota_exceeded",
    "monthly included credits",
    "payment required",
    "insufficient credits",
)


# Mã trạng thái 400/401/403 đứng thành từ riêng, không phải chữ số nằm trong một
# số dài hơn.
_STATUS_CODE_RE = re.compile(r"\b(400|401|403)\b")

# Lỗi cấu hình: khóa sai, không đủ quyền, tên model không tồn tại. Thử lại không
# bao giờ sửa được những thứ này.
_NOT_RETRYABLE_MARKERS = (
    "api key not valid",
    "api_key_invalid",
    "invalid_argument",
    "permission_denied",
    "invalid username or password",
    "unauthorized",
    "authentication",
    "not supported",
    "does not exist",
)


def _is_rate_limited(error: Exception) -> bool:
    text = str(error)
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower()


def _is_not_retryable(error: Exception) -> bool:
    """Lỗi mà thử lại chỉ tốn thời gian.

    Quan sát được khi kiểm thử chuỗi dự phòng: một khóa sai bị thử lại đủ ba lần
    ở mỗi nhà cung cấp trước khi chuỗi chịu chuyển làn. Với sáu stage mỗi truy
    vấn, một dòng `.env` gõ nhầm biến thành 36 lời gọi hỏng và hàng chục giây chờ
    — trong khi thông tin cần thiết đã có ngay từ lời gọi đầu tiên.

    Cố ý **không** mở cầu dao ở đây. Cầu dao dành cho thứ tự hết rồi tự khỏi
    (hạn mức). Khóa sai thì không tự khỏi, và mở cầu dao chỉ làm mờ nguyên nhân
    thật trong thông báo lỗi.
    """
    low = str(error).lower()
    if any(marker in low for marker in _NOT_RETRYABLE_MARKERS):
        return True
    # 401/403 luôn là cấu hình. 400 thì hoặc là prompt sai hoặc là tham số sai —
    # cả hai đều không đổi giữa các lần thử. Cần biên từ: không có nó thì một
    # thông báo chứa "11400" cũng bị coi là lỗi cấu hình.
    return bool(_STATUS_CODE_RE.search(low))


def _is_hard_quota(error: Exception) -> bool:
    """Hết hạn mức thật, không phải chặn tốc độ tạm thời.

    Phân biệt hai thứ này là bắt buộc. Bị chặn tốc độ trong một phút thì chờ rồi
    thử lại là đúng. Hết hạn mức theo ngày thì thử lại chỉ tốn thời gian: mỗi
    truy vấn gọi LLM tới sáu lần, mỗi lần ba lượt thử với backoff tăng dần, và
    hai mươi truy vấn sẽ ngồi chờ hàng chục phút cho một hạn mức không quay lại
    trước nửa đêm.
    """
    low = str(error).lower()
    return any(marker in low for marker in _HARD_QUOTA_MARKERS)


def _retry_delay(error: Exception | None, attempt: int) -> float:
    """Chờ bao lâu trước lần thử lại.

    Bị chặn tốc độ là nguyên nhân thất bại hay gặp nhất khi contextualise, vì
    bước đó sinh một lời gọi cho mỗi chunk. Lùi 1.5s rồi 3s là quá ngắn cho hạn
    mức tính theo phút: cả ba lần thử đều rơi vào cùng một cửa sổ và cùng hỏng.

    Google thường trả kèm `retryDelay` trong phần chi tiết lỗi — dùng con số đó
    khi có, vì đoán thì hoặc là chờ thừa hoặc là hỏng tiếp.
    """
    if error is not None:
        match = _RETRY_DELAY_RE.search(str(error))
        if match:
            return min(float(match.group(1)) + 1.0, 90.0)
        if _is_rate_limited(error):
            # Hạn mức thường tính theo phút; lùi đủ để sang cửa sổ mới.
            return min(20.0 * (attempt + 1), 90.0)
    return 1.5 * (2**attempt)


@dataclass
class LlmUsage:
    calls: Counter = field(default_factory=Counter)
    seconds: Counter = field(default_factory=Counter)
    failures: Counter = field(default_factory=Counter)

    def snapshot(self) -> dict:
        return {
            "calls": dict(self.calls),
            "seconds": {k: round(v, 2) for k, v in self.seconds.items()},
            "failures": dict(self.failures),
            "total_calls": sum(self.calls.values()),
        }


# =============================================================================
#  Lớp cơ sở — mọi thứ trừ lời gọi mạng
# =============================================================================


class BaseReader:
    #: Tên ngắn hiện trong `/health` và trong trace. Nhà cung cấp phải đặt lại.
    provider: str = "base"

    # Hệ số nới ngân sách token đầu ra.
    #
    # `gemini-flash-latest` bật thinking mặc định, và token suy nghĩ tính vào
    # chính `max_output_tokens`. Triệu chứng quan sát được: câu trả lời bị cắt
    # giữa chừng ("* Điểm trung") dù ngân sách 1024 token lẽ ra thừa sức, và
    # các stage chấm điểm với ngân sách 8 token trả về chuỗi rỗng nên
    # `grounded` luôn là None.
    #
    # SDK `google-genai==0.8.0` chưa có `ThinkingConfig.thinking_budget` để tắt
    # thinking — phiên bản này chỉ có `include_thoughts`. Nâng SDK sẽ kéo theo
    # rủi ro đổi API ở khắp pipeline, nên cách ít rủi ro nhất là nới ngân sách
    # để cả phần suy nghĩ lẫn phần trả lời cùng vừa.
    #
    # Với các model không có thinking (phần lớn model trên HF), nới ngân sách chỉ
    # là nới trần — không tốn thêm token nào, vì chúng dừng khi nói xong.
    #
    # `_MIN_OUTPUT_TOKENS` bảo đảm các stage chỉ cần một từ khóa
    # (SUPPORTED / SIMPLE) vẫn còn chỗ để nói ra nó sau khi đã suy nghĩ.
    _THINKING_HEADROOM = 3
    _MIN_OUTPUT_TOKENS = 256

    def __init__(
        self,
        *,
        model: str,
        timeout_s: int = 60,
        max_retries: int = 2,
        concurrency: int = 4,
        enabled: bool = True,
    ):
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.usage = LlmUsage()
        self._enabled = enabled

        # Chặn số lời gọi song song. Contextualisation ở §6 sinh một lời gọi cho
        # mỗi chunk; bắn cả nghìn lời gọi cùng lúc sẽ bị nhà cung cấp chặn tốc độ
        # và làm hỏng cả lần ingest.
        self._sem = asyncio.Semaphore(concurrency)

        # Cầu dao. Khi phát hiện hết hạn mức, mọi lời gọi tiếp theo hỏng ngay
        # trong `_breaker_cooldown_s` giây thay vì lặp lại vòng chờ vô ích.
        # Pipeline hạ cấp có kiểm soát: truy xuất, xếp hạng và cổng abstention
        # vẫn chạy, chỉ phần sinh văn bản là báo lỗi rõ ràng.
        self._breaker_open_until: float = 0.0
        self._breaker_reason: str = ""
        self._breaker_cooldown_s: int = 900

        # Cầu dao ngắn cho việc bị chặn tốc độ. Ngắn hơn hẳn cầu dao hạn mức vì
        # hai thứ này khác nhau: hết hạn mức theo ngày thì không quay lại trước
        # nửa đêm, còn bị chặn theo phút thì hết phút là dùng lại được. Nghỉ 15
        # phút cho một giới hạn tính theo phút là tự cấm mình dùng một khóa vẫn
        # còn tốt.
        self._rate_limit_cooldown_s: int = 60

    # ------------------------------------------------------------------ trạng thái

    @property
    def available(self) -> bool:
        return self._enabled and not self.circuit_open

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self._breaker_open_until

    @property
    def circuit_reason(self) -> str:
        return self._breaker_reason if self.circuit_open else ""

    def _open_circuit(self, reason: str, cooldown_s: int | None = None) -> None:
        cooldown = self._breaker_cooldown_s if cooldown_s is None else cooldown_s
        self._breaker_open_until = time.monotonic() + cooldown
        self._breaker_reason = reason
        log.error("Ngắt mạch %s trong %ds: %s", self.provider, cooldown, reason)

    def reset_circuit(self) -> None:
        """Đóng lại cầu dao. Gọi sau khi đã thay khóa API."""
        self._breaker_open_until = 0.0
        self._breaker_reason = ""

    def status(self) -> dict:
        """Mô tả ngắn cho `/health` — vận hành viên cần biết đang dùng cái gì."""
        return {
            "provider": self.provider,
            "model": self.model,
            "configured": self._enabled,
            "available": self.available,
            "circuit_open": self.circuit_open,
            "circuit_reason": self.circuit_reason,
        }

    # ------------------------------------------------------------------ nhà cung cấp cài

    async def _generate(
        self,
        prompt: str,
        *,
        system: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        raise NotImplementedError

    def _unconfigured_message(self) -> str:
        return (
            f"Chưa cấu hình khóa API cho {self.provider}. Mọi bước cần mô hình ngôn ngữ "
            "(định tuyến, chấm căn cứ, sinh câu trả lời, kiểm chứng) đều không chạy được."
        )

    # ------------------------------------------------------------------ gọi 1 lần

    async def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_output_tokens: int = 1024,
        temperature: float = 0.0,
        tag: str = "misc",
    ) -> str:
        if not self._enabled:
            raise LlmUnavailable(self._unconfigured_message())
        if self.circuit_open:
            raise LlmUnavailable(self._breaker_reason)

        budget = max(max_output_tokens * self._THINKING_HEADROOM, self._MIN_OUTPUT_TOKENS)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.time()
            try:
                async with self._sem:
                    text = await asyncio.wait_for(
                        self._generate(
                            prompt,
                            system=system,
                            max_output_tokens=budget,
                            temperature=temperature,
                        ),
                        timeout=self.timeout_s,
                    )
                self.usage.calls[tag] += 1
                self.usage.seconds[tag] += time.time() - t0
                return text.strip()
            except asyncio.TimeoutError as e:
                last_error = e
                self.usage.failures[f"{tag}:timeout"] += 1
                log.warning("LLM timeout ở stage %s (lần %d)", tag, attempt + 1)
            except LlmUnavailable:
                raise
            except Exception as e:  # noqa: BLE001
                last_error = e
                if _is_hard_quota(e):
                    self.usage.failures[f"{tag}:quota_exhausted"] += 1
                    self._open_circuit(
                        f"Hạn mức của khóa {self.provider} đã cạn. Truy xuất, xếp hạng và cổng "
                        "từ chối vẫn hoạt động, nhưng không sinh được câu trả lời cho tới khi "
                        "thay khóa."
                    )
                    raise LlmUnavailable(self._breaker_reason) from e

                if _is_not_retryable(e):
                    self.usage.failures[f"{tag}:config"] += 1
                    log.error("Lỗi cấu hình %s ở stage %s: %s", self.provider, tag, str(e)[:200])
                    raise LlmUnavailable(
                        f"{self.provider} từ chối lời gọi vì cấu hình, thử lại không giúp "
                        f"(stage {tag}): {e}"
                    ) from e

                kind = "rate_limit" if _is_rate_limited(e) else "error"
                self.usage.failures[f"{tag}:{kind}"] += 1
                log.warning("LLM %s ở stage %s (lần %d): %s", kind, tag, attempt + 1, str(e)[:200])

            if attempt < self.max_retries:
                delay = _retry_delay(last_error, attempt)
                log.debug("Chờ %.1fs rồi thử lại stage %s", delay, tag)
                await asyncio.sleep(delay)

        # Hết lượt thử vì bị chặn tốc độ: mở cầu dao ngắn thay vì để stage sau
        # khám phá lại đúng điều vừa biết, với đúng cái giá vừa trả.
        #
        # Đây là lập luận đã dùng cho khóa sai ở `_is_not_retryable`, áp cho một
        # nguyên nhân khác. Một truy vấn gọi LLM bốn lần; nếu nhà cung cấp vừa
        # hỏng ba lượt liền vì 429 thì stage tiếp theo gần như chắc chắn cũng
        # hỏng, và backoff 20s + 40s sẽ được trả lại nguyên vẹn cho từng stage.
        # Đo được ngày 12/08/2026: truy vấn 37.7s kéo lên 89.8–105.9s vì đúng
        # chuyện này.
        #
        # Chỉ mở cho chặn tốc độ. Lỗi thoáng qua (503, đứt mạng) không phải lý
        # do cấm cả một nhà cung cấp.
        if last_error is not None and _is_rate_limited(last_error):
            self._open_circuit(
                f"{self.provider} đang bị chặn tốc độ. Tạm nghỉ "
                f"{self._rate_limit_cooldown_s}s rồi dùng lại.",
                cooldown_s=self._rate_limit_cooldown_s,
            )

        raise LlmUnavailable(
            f"Không gọi được {self.provider} sau {self.max_retries + 1} lần thử "
            f"(stage {tag}): {last_error}"
        )

    # -------------------------------------------------------------------- batch

    async def batch(
        self,
        prompts: list[str],
        *,
        system: str | None = None,
        max_output_tokens: int = 128,
        tag: str = "batch",
    ) -> list[str | None]:
        """Chạy nhiều prompt song song có giới hạn.

        Trả `None` cho prompt lỗi thay vì ném exception: dùng cho
        contextualisation, nơi mất ngữ cảnh của vài chunk trong số hàng trăm là
        chấp nhận được, còn hỏng cả lần ingest thì không.
        """

        async def one(p: str) -> str | None:
            try:
                return await self.chat(p, system=system, max_output_tokens=max_output_tokens, tag=tag)
            except LlmUnavailable:
                return None

        return await asyncio.gather(*(one(p) for p in prompts))

    # ------------------------------------------------------------------- yes/no

    async def yes_no(self, question: str, *, tag: str = "judge") -> bool | None:
        """Phán quyết nhị phân dùng cho các bước chấm. `None` = không phân tích được."""
        raw = await self.chat(
            question,
            system="Trả lời đúng một từ: YES hoặc NO.",
            max_output_tokens=8,
            tag=tag,
        )
        v = raw.upper()
        if "YES" in v:
            return True
        if "NO" in v:
            return False
        return None


# =============================================================================
#  Gemini
# =============================================================================


class GeminiReader(BaseReader):
    provider = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: int = 60,
        max_retries: int = 2,
        concurrency: int = 4,
    ):
        super().__init__(
            model=model,
            timeout_s=timeout_s,
            max_retries=max_retries,
            concurrency=concurrency,
            enabled=bool(api_key),
        )
        self._api_key = api_key
        self._client = None

    def _unconfigured_message(self) -> str:
        return (
            "Chưa cấu hình GEMINI_API_KEY. Mọi bước cần mô hình ngôn ngữ "
            "(định tuyến, chấm căn cứ, sinh câu trả lời, kiểm chứng) đều "
            "không chạy được."
        )

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def _generate(
        self,
        prompt: str,
        *,
        system: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        from google.genai import types

        client = self._get_client()
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            **({"system_instruction": system} if system else {}),
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""


# =============================================================================
#  Hugging Face Inference Providers
# =============================================================================


class HuggingFaceReader(BaseReader):
    """Router của Hugging Face, giao thức tương thích OpenAI.

    Dùng `httpx` thẳng thay vì thêm SDK. Endpoint `/v1/chat/completions` của
    router ổn định và đã tương thích OpenAI, nên một SDK chỉ thêm phụ thuộc mà
    không thêm gì về mặt ngữ nghĩa — trong khi phần thực sự khó (cầu dao, thử
    lại) đã nằm ở `BaseReader` rồi.

    Model mặc định thuộc họ Qwen là có chủ ý: notebook gốc dùng Qwen2.5-7B, nên
    chạy Qwen qua router giữ hệ thống gần bản tham chiếu hơn là đổi hẳn họ model.

    Router chuyển tiếp tới nhiều nhà cung cấp phía sau (Together, Fireworks,
    Nebius, Groq…). Chúng trả mã lỗi khác nhau cho cùng một tình huống, nên phần
    đọc lỗi bên dưới lấy cả `message` lẫn `error` từ thân phản hồi thay vì chỉ
    dựa vào mã trạng thái.
    """

    provider = "huggingface"

    DEFAULT_BASE_URL = "https://router.huggingface.co/v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: int = 90,
        max_retries: int = 2,
        concurrency: int = 4,
    ):
        super().__init__(
            model=model,
            timeout_s=timeout_s,
            max_retries=max_retries,
            concurrency=concurrency,
            enabled=bool(api_key),
        )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = None

    def _unconfigured_message(self) -> str:
        return (
            "Chưa cấu hình HF_API_KEY. Mọi bước cần mô hình ngôn ngữ "
            "(định tuyến, chấm căn cứ, sinh câu trả lời, kiểm chứng) đều "
            "không chạy được."
        )

    def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                # Timeout thật nằm ở `asyncio.wait_for` của BaseReader; đặt ở
                # đây cao hơn một chút để lớp ngoài là lớp quyết định, tránh hai
                # đồng hồ đếm ngược tranh nhau báo lỗi khác kiểu.
                timeout=self.timeout_s + 15,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _generate(
        self,
        prompt: str,
        *,
        system: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        client = self._get_client()

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_output_tokens,
                "stream": False,
            },
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"HTTP {response.status_code} từ router Hugging Face: "
                f"{self._error_detail(response)}"
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            # Một số nhà cung cấp trả 200 kèm `error` trong thân phản hồi. Coi đó
            # là thành công sẽ biến lỗi hạn mức thành câu trả lời rỗng, và các
            # stage chấm điểm sẽ lặng lẽ trả về None.
            raise RuntimeError(
                f"Router Hugging Face không trả lựa chọn nào: {self._error_detail(response)}"
            )

        return choices[0].get("message", {}).get("content") or ""

    @staticmethod
    def _error_detail(response) -> str:
        """Rút phần người đọc được từ thân lỗi, dù nhà cung cấp gói kiểu gì."""
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError):
            return response.text[:300]

        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)[:300]
            if error:
                return str(error)[:300]
            if body.get("message"):
                return str(body["message"])[:300]
        return str(body)[:300]


# =============================================================================
#  Chuỗi dự phòng
# =============================================================================


class ChainReader(BaseReader):
    """Thử lần lượt nhiều reader; chuyển làn khi cầu dao của cái trước mở.

    Vì sao cần: hạn mức miễn phí của bất kỳ nhà cung cấp nào cũng đủ nhỏ để cạn
    giữa buổi trình bày. Với một reader duy nhất, cạn hạn mức nghĩa là mất hẳn
    phần sinh câu trả lời. Với chuỗi, nó là một dòng trong trace.

    Lớp này cố tình **không** kế thừa logic thử lại của `BaseReader`: mỗi reader
    con đã tự thử lại rồi. Chồng thêm một vòng nữa sẽ nhân số lần gọi lên và làm
    độ trễ khi hỏng trở nên khó lường.
    """

    provider = "chain"

    def __init__(self, readers: list[BaseReader]):
        if not readers:
            raise ValueError("ChainReader cần ít nhất một reader")
        # Không gọi super().__init__: mọi trạng thái đều nằm ở reader con.
        self.readers = readers
        self.usage = LlmUsage()
        self.model = " → ".join(f"{r.provider}:{r.model}" for r in readers)
        #: Nhà cung cấp đã phục vụ lời gọi gần nhất — orchestrator ghi vào trace.
        self.last_provider: str = ""
        self.last_model: str = ""

    @property
    def available(self) -> bool:
        return any(r.available for r in self.readers)

    @property
    def circuit_open(self) -> bool:
        return not self.available

    @property
    def circuit_reason(self) -> str:
        if self.available:
            return ""
        reasons = [f"{r.provider}: {r.circuit_reason or 'chưa cấu hình'}" for r in self.readers]
        return "Mọi nhà cung cấp đều không dùng được — " + "; ".join(reasons)

    def reset_circuit(self) -> None:
        for r in self.readers:
            r.reset_circuit()

    def status(self) -> dict:
        return {
            "provider": "chain",
            "model": self.model,
            "configured": any(r._enabled for r in self.readers),
            "available": self.available,
            "circuit_open": self.circuit_open,
            "circuit_reason": self.circuit_reason,
            "last_used": self.last_provider,
            "members": [r.status() for r in self.readers],
        }

    async def chat(self, prompt: str, **kwargs) -> str:
        errors: list[str] = []
        for reader in self.readers:
            if not reader.available:
                errors.append(f"{reader.provider}: {reader.circuit_reason or 'chưa cấu hình'}")
                continue
            try:
                text = await reader.chat(prompt, **kwargs)
                if self.last_provider and self.last_provider != reader.provider:
                    log.warning(
                        "Chuyển nhà cung cấp mô hình ngôn ngữ: %s → %s",
                        self.last_provider,
                        reader.provider,
                    )
                self.last_provider = reader.provider
                self.last_model = reader.model
                self.usage.calls[kwargs.get("tag", "misc")] += 1
                return text
            except LlmUnavailable as e:
                errors.append(f"{reader.provider}: {e}")
                self.usage.failures[f"{reader.provider}:unavailable"] += 1
                log.warning("Reader %s không dùng được, thử cái tiếp theo", reader.provider)

        raise LlmUnavailable("Không nhà cung cấp nào trả lời được — " + "; ".join(errors))
