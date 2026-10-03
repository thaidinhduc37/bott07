# =============================================================================
#  Backend (FastAPI + RAG pipeline trong cùng một tiến trình) — dev
#
#  Build từ thư mục server/:   docker build -t sa-server-dev server
#  Mã nguồn được bind-mount lúc chạy (xem docker-compose.dev.yml), nên image
#  chỉ chứa thư viện Python.
# =============================================================================

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models

WORKDIR /app/server

# torch CPU phải cài trước, từ index riêng, để không kéo bản CUDA ~2.5 GB.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

EXPOSE 5000
CMD ["python", "main.py"]
