"""§2 Models: encoder BGE-M3 và cross-encoder bge-reranker-v2-m3 chạy trên CPU (reader là Gemini, xem `llm.py`).

Encoder chạy cùng chỗ với chỉ mục để không tốn quota và độ trễ mạng cho mỗi chunk và mỗi truy vấn. Cross-encoder tạo điểm
số để đặt ngưỡng abstention (§14) và không có API công cộng nào trả đúng điểm đó. Hai model chiếm ~4,5 GB RAM ở fp32 và
được nạp lười ở request đầu tiên; đặt `PRELOAD_MODELS=1` để nạp ngay lúc khởi động.
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
        """Tokenizer của chính encoder: chunking đo ngân sách bằng token này, dùng tokenizer khác thì chunk 400 token đo được có
        thể là 520 token thật và bị cắt cụt lúc nhúng."""
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
                            # Lượng tử hóa động int8 cho các lớp Linear: nhanh gấp 2,4 lần (3532 → 1471 ms mỗi cặp), điểm gần như không đổi
                            # (0.9930 → 0.9864 trong phạm vi). Phải chạy lại scripts/calibrate_tau.py sau khi bật hoặc tắt vì τ calibrate trên thang
                            # điểm này; scripts/quantize_models.py ghi sẵn file int8 để tránh đỉnh RAM khi chuyển đổi lúc chạy.
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
        """Độ liên quan của cặp (truy vấn, đoạn văn) trong [0, 1]. Một số phiên bản sentence-transformers trả logit thô nên đưa
        qua sigmoid khi giá trị ngoài [0, 1]: τ được calibrate trên thang [0, 1]."""
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
