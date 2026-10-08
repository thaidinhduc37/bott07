"""Single entrypoint for the unified server: `cd server && python main.py`.

Starts the merged FastAPI app (`app.main:app` — api-py's web layer + the
rag-service pipeline running in-process, see `app/pipeline/container.py` and
`app/services/rag_client.py`) with uvicorn, listening on API_PORT (.env,
default 5000 — matches the client's VITE_API_URL=http://localhost:5000/api).

Requires (started separately, both via Docker — see repo root
docker-compose.dev.yml):
  * PostgreSQL reachable at DATABASE_URL
  * ChromaDB reachable at CHROMA_HOST:CHROMA_PORT
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from app.core.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    workers = settings.api_workers
    if workers > 1 and sys.platform == "win32":
        # Trên Windows nhiều tiến trình dùng chung một cổng làm một phần kết nối bị treo 20–30 giây khi mở đồng loạt.
        logging.getLogger("uvicorn.error").warning("API_WORKERS=%d bị bỏ qua trên Windows: chạy 1 tiến trình (dùng Linux để chạy nhiều).", workers)
        workers = 1
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        workers=workers,
        # Mặc định uvicorn đóng kết nối nhàn rỗi sau 5 giây, ngắn hơn thời gian suy nghĩ giữa hai thao tác nên mỗi yêu cầu phải mở kết nối mới.
        timeout_keep_alive=65,
        reload=False,
    )
