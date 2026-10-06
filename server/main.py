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

import uvicorn

from app.core.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=False,
    )
