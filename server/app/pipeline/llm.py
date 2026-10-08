"""Client LLM (Gemini) cho mọi stage sinh văn bản của pipeline.

`BaseReader` giữ phần khó: cầu dao, lùi-thử-lại theo `retryDelay`, phân biệt hết hạn mức với chặn tốc độ, đếm lời gọi
theo stage và ngân sách token cho model có thinking; nhà cung cấp chỉ cài `_generate()`. Sinh văn bản greedy
(`temperature=0`) để kết quả lặp lại được; `yes_no` trả `None` khi không phân tích được thay vì ép thành `False`.
"""

from __future__ import annotations

import asyncio
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

# Dấu hiệu Google API khi khóa hết hạn mức (khác với 429 tạm thời).
_HARD_QUOTA_MARKERS = (
    "exceeded your current quota",
    "check your plan and billing",
    "billing details",
    "quota_exceeded",
)


# Mã 400/401/403 đứng thành từ riêng, không phải một phần của số dài hơn.
_STATUS_CODE_RE = re.compile(r"\b(400|401|403)\b")

# Lỗi cấu hình (khóa sai, thiếu quyền, model không tồn tại): thử lại không sửa được.
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
    # 401/403 luôn là cấu hình; 400 là prompt hoặc tham số sai, không đổi giữa các lần thử. Cần biên từ để "11400" không khớp.
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


# --- Lớp cơ sở — mọi thứ trừ lời gọi mạng ---


class BaseReader:
    #: Tên ngắn hiện trong `/health` và trong trace. Nhà cung cấp phải đặt lại.
    provider: str = "base"

    # `gemini-flash-latest` bật thinking và token suy nghĩ tính vào `max_output_tokens`: ngân sách nhỏ làm câu trả lời bị cắt
    # hoặc stage chấm điểm trả chuỗi rỗng. SDK đang dùng chưa tắt được thinking nên nới ngân sách thay vì nâng SDK.
    # `_MIN_OUTPUT_TOKENS` chừa chỗ cho stage chỉ cần một từ khóa (SUPPORTED / SIMPLE).
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

        # Giới hạn lời gọi song song: ingest sinh một lời gọi cho mỗi chunk, bắn cả nghìn lời gọi sẽ bị chặn tốc độ.
        self._sem = asyncio.Semaphore(concurrency)

        # Cầu dao hạn mức: sau khi hết hạn mức mọi lời gọi hỏng ngay trong `_breaker_cooldown_s` giây; truy xuất và cổng
        # abstention vẫn chạy, chỉ phần sinh văn bản báo lỗi rõ ràng.
        self._breaker_open_until: float = 0.0
        self._breaker_reason: str = ""
        self._breaker_cooldown_s: int = 900

        # Cầu dao chặn tốc độ ngắn hơn hẳn: chặn theo phút thì hết phút là dùng lại được, không cần nghỉ cả 15 phút.
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

        # Hết lượt thử vì bị chặn tốc độ: mở cầu dao ngắn để các stage sau không lặp lại backoff (đo được một truy vấn từ
        # 37,7s lên ~90–106s). Lỗi thoáng qua (503, đứt mạng) không mở cầu dao.
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


# --- Gemini ---


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
