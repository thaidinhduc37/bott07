"""§2 Models — encoder và cross-encoder chạy trên CPU.

Notebook tải ba model: reader Qwen2.5-7B 4-bit, encoder BGE-M3, và cross-encoder
bge-reranker-v2-m3, tất cả trên GPU T4. Ở đây reader được thay bằng Gemini API
(xem `llm.py`), còn hai model còn lại vẫn chạy cục bộ trên CPU vì:

* **Encoder** phải chạy cùng chỗ với chỉ mục. Gọi API cho mỗi chunk lúc ingest và
  mỗi truy vấn lúc hỏi vừa tốn quota vừa thêm độ trễ mạng vào đường nóng.
* **Cross-encoder** là thứ tạo ra điểm số để đặt ngưỡng abstention (§14). Không
  có nó thì lớp phòng thủ số 1 chống bịa câu trả lời biến mất, và không có API
  công cộng nào trả về đúng điểm số đó.

Hai model cộng lại chiếm khoảng 4.5 GB RAM ở fp32. Chúng được **nạp lười**: quá
trình khởi động không đụng tới chúng, nên `/health` trả lời ngay và container
lên nhanh. Đặt `PRELOAD_MODELS=1` nếu muốn trả cái giá đó lúc khởi động thay vì
ở request đầu tiên.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import numpy as np

log = logging.getLogger("rag.models")


class ModelRegistry:
    """Giữ encoder, tokenizer và reranker. An toàn khi gọi từ nhiều luồng."""

    def __init__(
        self,
        embedding_model: str,
        reranker_model: str,
        quantize_reranker: bool = True,
        quantize_encoder: bool = True,
        quantized_dir: Path | None = None,
    ):
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.quantize_reranker = quantize_reranker
        self.quantize_encoder = quantize_encoder
        self.quantized_dir = quantized_dir
        self._embedder = None
        self._tokenizer = None
        self._reranker = None
        # Uvicorn chạy handler đồng bộ trong threadpool, nên hai request đến cùng
        # lúc có thể cùng kích hoạt việc nạp model. Nạp hai lần model 2 GB trên
        # máy 16 GB là đủ để đẩy hệ thống vào swap.
        self._lock = threading.Lock()

    def _quantized_path(self, name: str) -> Path | None:
        if self.quantized_dir is None:
            return None
        path = self.quantized_dir / f"{name}_int8.pt"
        return path if path.exists() else None

    # ------------------------------------------------------------------ encoder

    @property
    def embedder(self):
        if self._embedder is None:
            with self._lock:
                if self._embedder is None:
                    import torch

                    t0 = time.time()
                    prebuilt = self._quantized_path("encoder") if self.quantize_encoder else None
                    if prebuilt:
                        log.info("Đang nạp encoder int8 dựng sẵn từ %s…", prebuilt)
                        self._embedder = torch.load(prebuilt, weights_only=False, map_location="cpu")
                    else:
                        from sentence_transformers import SentenceTransformer

                        log.info("Đang nạp encoder %s (CPU)…", self.embedding_model)
                        model = SentenceTransformer(self.embedding_model, device="cpu")
                        if self.quantize_encoder:
                            # Chuyển đổi lúc chạy: bản fp32 và bản int8 cùng tồn tại
                            # trong RAM một lúc. Chạy scripts/quantize_models.py trước
                            # để ghi sẵn file int8 và tránh đỉnh RAM này.
                            model = torch.quantization.quantize_dynamic(
                                model, {torch.nn.Linear}, dtype=torch.qint8
                            )
                            log.info("Encoder đã lượng tử hóa int8 (lúc chạy)")
                        self._embedder = model
                    log.info("Encoder sẵn sàng sau %.1fs", time.time() - t0)
        return self._embedder

    @property
    def tokenizer(self):
        """Tokenizer của chính encoder.

        Chunking đo ngân sách bằng token của encoder, nên đây phải là **cùng**
        tokenizer chứ không phải một cái xấp xỉ. Dùng tokenizer khác thì chunk
        400 token đo được có thể là 520 token thật và bị cắt cụt lúc nhúng.
        """
        if self._tokenizer is None:
            with self._lock:
                if self._tokenizer is None:
                    from transformers import AutoTokenizer

                    self._tokenizer = AutoTokenizer.from_pretrained(self.embedding_model)
        return self._tokenizer

    # ----------------------------------------------------------------- reranker

    @property
    def reranker(self):
        if self._reranker is None:
            with self._lock:
                if self._reranker is None:
                    import torch

                    t0 = time.time()
                    prebuilt = self._quantized_path("reranker") if self.quantize_reranker else None
                    if prebuilt:
                        log.info("Đang nạp cross-encoder int8 dựng sẵn từ %s…", prebuilt)
                        self._reranker = torch.load(prebuilt, weights_only=False, map_location="cpu")
                    else:
                        from sentence_transformers import CrossEncoder

                        log.info("Đang nạp cross-encoder %s (CPU)…", self.reranker_model)
                        model = CrossEncoder(self.reranker_model, max_length=512, device="cpu")

                        if self.quantize_reranker:
                            # Lượng tử hóa động: trọng số các lớp Linear về int8, kích
                            # hoạt vẫn float. Không cần dữ liệu hiệu chỉnh.
                            #
                            # Đo được trên máy này: 3532 → 1471 ms mỗi cặp (2.4×), còn
                            # điểm số gần như không đổi (0.9930 → 0.9864 ở câu trong
                            # phạm vi; 0.0019 ở câu ngoài phạm vi). Điều đó quan trọng
                            # hơn tốc độ: ngưỡng abstention τ được calibrate trên chính
                            # thang điểm này, nên một phép tối ưu làm dịch điểm sẽ âm
                            # thầm làm sai cổng chống bịa.
                            #
                            # Vẫn phải chạy lại scripts/calibrate_tau.py sau khi bật/tắt
                            # tùy chọn này. Chuyển đổi lúc chạy: bản fp32 và bản int8
                            # cùng tồn tại trong RAM một lúc — scripts/quantize_models.py
                            # ghi sẵn file int8 để tránh đỉnh RAM này.
                            model.model = torch.quantization.quantize_dynamic(
                                model.model, {torch.nn.Linear}, dtype=torch.qint8
                            )
                            log.info("Cross-encoder đã lượng tử hóa int8 (lúc chạy)")

                        self._reranker = model
                    log.info("Cross-encoder sẵn sàng sau %.1fs", time.time() - t0)
        return self._reranker

    # -------------------------------------------------------------------- API

    def encode(self, texts: list[str], batch_size: int = 8) -> np.ndarray:
        """Nhúng và chuẩn hóa. Batch nhỏ vì CPU không hưởng lợi từ batch lớn
        như GPU, còn batch lớn thì đỉnh RAM cao hơn hẳn."""
        return self.embedder.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)

    def rerank_scores(self, pairs: list[tuple[str, str]], batch_size: int = 8) -> np.ndarray:
        """Độ liên quan của cặp (truy vấn, đoạn văn), đưa về [0, 1].

        Một số phiên bản sentence-transformers trả logit thô thay vì xác suất.
        Đưa qua sigmoid khi phát hiện giá trị ngoài [0,1] — bước này bắt buộc, vì
        ngưỡng τ được calibrate trên thang [0,1] và so logit với τ thì vô nghĩa.
        """
        if not pairs:
            return np.zeros(0, dtype=np.float32)
        scores = np.asarray(
            self.reranker.predict(pairs, batch_size=batch_size, show_progress_bar=False),
            dtype=np.float32,
        ).reshape(-1)
        if scores.min() < 0.0 or scores.max() > 1.0:
            scores = 1.0 / (1.0 + np.exp(-scores))
        return scores

    def warmup(self) -> None:
        self.encode(["khởi động"])
        self.rerank_scores([("khởi động", "khởi động")])

    @property
    def loaded(self) -> dict[str, bool]:
        return {
            "encoder": self._embedder is not None,
            "reranker": self._reranker is not None,
        }
