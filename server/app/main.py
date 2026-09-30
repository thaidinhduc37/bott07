"""FastAPI app entrypoint — the unified `server/app`.

Merges what used to be two processes:

  * `server/api-py` — auth, users, audit, health, chat, documents (web/DB layer)
  * `server/rag-service` — hybrid retrieval, rerank, abstention, groundedness,
    Gemini→HF LLM fallback (RAG pipeline)

into one FastAPI app, one process, one `python main.py`. The RAG pipeline is
built once at startup (`app.rag_container.get_rag_container()`) and called
directly in Python from `app/services/rag_client.py` — no more HTTP hop to
`localhost:8000`, no `X-Internal-Token`.

Mirrors api-py's original `main.py`: global `/api` prefix, cookie-based auth,
CORS (env-driven), Nest-shaped `{message, code}` JSON error bodies.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.rag_container import get_rag_container
from app.routers.approvals import router as approvals_router
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.catalog import router as catalog_router
from app.routers.faculties import router as faculties_router
from app.routers.rooms import router as rooms_router
from app.routers.courses import classes_router, router as courses_router
from app.routers.documents import router as documents_router
from app.routers.chat import admin_dashboard_router as chat_admin_dashboard_router
from app.routers.forms import router as forms_router
from app.routers.health import router as health_router
from app.routers.learning import router as learning_router
from app.routers.notifications import router as notifications_router
from app.routers.schedules import router as schedules_router
from app.routers.users import admin_audit_router, admin_users_router, users_router
from app.services import study_reminders
from app.services.rag_client import get_rag_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

settings = get_settings()

app = FastAPI(title="student-assistant", version="1.0.0")

# ------------------------------------------------------------------- CORS
if settings.cors_origin == "*":
    _cors_kwargs = {"allow_origin_regex": ".*"}
elif settings.cors_origin:
    _cors_kwargs = {"allow_origins": [o.strip() for o in settings.cors_origin.split(",")]}
else:
    _cors_kwargs = {"allow_origins": [f"http://localhost:{settings.web_port}"]}

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    **_cors_kwargs,
)


# --------------------------------------------------------- exception shapes

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    body = detail if isinstance(detail, dict) else {"message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    messages = [f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in errors]
    return JSONResponse(
        status_code=400,
        content={"message": "; ".join(messages) or "Dữ liệu không hợp lệ", "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"message": "Đã xảy ra lỗi hệ thống", "code": "INTERNAL_ERROR"})


# ------------------------------------------------------------------ routers

api_prefix = f"/{settings.api_prefix}" if not settings.api_prefix.startswith("/") else settings.api_prefix

app.include_router(health_router, prefix=api_prefix)
app.include_router(auth_router, prefix=api_prefix)
app.include_router(users_router, prefix=api_prefix)
app.include_router(admin_users_router, prefix=api_prefix)
app.include_router(admin_audit_router, prefix=api_prefix)
app.include_router(chat_router, prefix=api_prefix)
app.include_router(chat_admin_dashboard_router, prefix=api_prefix)
app.include_router(learning_router, prefix=api_prefix)
app.include_router(documents_router, prefix=api_prefix)
app.include_router(courses_router, prefix=api_prefix)
app.include_router(classes_router, prefix=api_prefix)
app.include_router(catalog_router, prefix=api_prefix)
app.include_router(faculties_router, prefix=api_prefix)
app.include_router(rooms_router, prefix=api_prefix)
app.include_router(forms_router, prefix=api_prefix)
app.include_router(approvals_router, prefix=api_prefix)
app.include_router(schedules_router, prefix=api_prefix)
app.include_router(notifications_router, prefix=api_prefix)


@app.on_event("startup")
async def on_startup() -> None:
    origin_desc = "* (reflect request Origin)" if settings.cors_origin == "*" else str(_cors_kwargs)
    logger.info(f"server ready at http://localhost:{settings.api_port}{api_prefix}")
    logger.info(f"CORS allowed: {origin_desc}")

    # Build the RAG pipeline container now (models are still lazy-loaded on
    # first use unless PRELOAD_MODELS=1 — see ModelRegistry).
    logger.info(f"  chroma     : {settings.chroma_host}:{settings.chroma_port}")
    logger.info(f"  encoder    : {settings.embedding_model} (dim {settings.embedding_dim}, CPU)")
    logger.info(f"  reranker   : {settings.reranker_model} (CPU)")
    c = get_rag_container()
    logger.info(f"  reader     : {c.reader.model} ({c.reader.provider})")
    logger.info(f"  τ khởi đầu : {settings.answer_threshold:.3f}")

    if not c.reader.available:
        logger.warning(
            "Chưa cấu hình khóa cho nhà cung cấp mô hình ngôn ngữ nào (GEMINI_API_KEY "
            "hoặc HF_API_KEY). Truy xuất vẫn chạy, nhưng định tuyến, chấm căn cứ, "
            "sinh câu trả lời và kiểm chứng đều sẽ báo lỗi."
        )

    if settings.preload_models:
        logger.info("PRELOAD_MODELS=1 — nạp encoder và reranker ngay bây giờ…")
        c.models.warmup()
        logger.info("Model đã sẵn sàng")
    else:
        logger.info("Model sẽ được nạp ở request đầu tiên (PRELOAD_MODELS=0)")

    study_reminders.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await study_reminders.stop()
    await get_rag_client().aclose()
    from app.pipeline import blocking

    blocking.shutdown(wait=False)
