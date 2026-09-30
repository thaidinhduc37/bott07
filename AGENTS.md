# AGENTS.md

Student assistant MVP for a security academy: RAG chat over regulations/curricula with
verifiable citations, class/exam schedules, auto-filled administrative forms with internal
e-signatures and a two-tier approval flow.

## Stack & layout

```
React/Vite (5173) ──► NestJS API (5000) ──┬──► PostgreSQL (5433)
                                          ├──► storage/ on disk
                                          └──► FastAPI RAG (8000) ──┬──► Qdrant (6333)
                                                                    └──► LLM fallback chain
                                                                         Gemini → Hugging Face
```

- `client/` — React + Vite + TypeScript SPA. Workspace-role-based layouts (STUDENT / APPROVER /
  ACADEMIC_MANAGER / LECTURER / ADMIN).
- `server/api/` — NestJS + Prisma + PostgreSQL. Owns auth, RBAC, forms/approval engine, documents,
  chat history, schedules, notifications, audit log. Calls `server/rag-service` over HTTP for
  anything RAG-related.
- `server/rag-service/` — Python FastAPI. Hybrid retrieval (BGE-M3 dense ∥ BM25+pyvi → RRF) →
  int8 cross-encoder rerank → calibrated abstention gate → retrieve-grade-rewrite loop →
  cited generation → groundedness verification. LLM fallback chain: Gemini → Hugging Face.
- `notebooks/rag-pipeline-2026.ipynb` — the original research notebook the RAG service is a
  CPU-only port of.
- `scripts/` — PowerShell orchestration (`chay.ps1`/`dung.ps1` run/stop everything in the right
  order, `cai-dat.ps1` setup, `sao-luu.ps1`/`khoi-phuc.ps1` backup/restore) and Python maintenance
  scripts (`ingest_corpus.py`, `calibrate_tau.py`, `download_models.py`).

When exploring code, prefer `.codegraph/` (CodeGraph MCP `codegraph_explore`, or
`codegraph explore "<query>"` via CLI) over grep/find/Read — it returns verbatim source plus call
paths in one round trip.

## Commands

```bash
cp .env.example .env       # fill in GEMINI_API_KEY and/or HF_API_KEY
npm install                # installs client + server/api workspaces
npm run infra:up           # PostgreSQL + Qdrant via Docker
npm run db:migrate
npm run db:seed            # demo data from real CSVs; ingest_corpus.py depends on this

npm run chay                # start everything (dev), waits for each layer to actually respond
npm run chay -- -SanPham    # start built/production bundles
npm run chay -- -ChiHaTang  # infra only, run the rest by hand
npm run dung                 # stop web/api/rag, keep infra
npm run dung -- -CaHaTang    # stop infra too

npm run dev:api / dev:web    # run one service directly
npm run build:api / build:web
npm run db:reset
npm run test:all             # scripts/test/chay-tat-ca.ps1
npm run test:ram             # scripts/test/do-ram.ps1

npm run docker:dev / docker:dev:down
npm run docker:prod / docker:prod:down
```

RAG service (separate venv — CPU torch needs its own index URL):

```bash
cd server/rag-service
python -m venv .venv
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/pip install -r requirements.txt
python ../../scripts/download_models.py    # BGE-M3 + reranker, ~2.5 GB
python ../../scripts/quantize_models.py    # pre-quantize both to int8, avoids fp32+int8 RAM peak at runtime

python scripts/ingest_corpus.py --only quyche   # requires db:seed to have run first
python scripts/calibrate_tau.py                 # then update ANSWER_THRESHOLD in .env
```

Run `quantize_models.py` after `download_models.py` and after any model change; re-run
`calibrate_tau.py` afterward since quantized reranker scores shift slightly (see
`server/rag-service/app/pipeline/models.py`).

Changing the corpus requires recalibrating τ — a stale threshold either abstains needlessly or
starts hallucinating.

## Conventions to know before editing

- Enter the app via `localhost`, not `127.0.0.1` — API CORS only allows `localhost:5173`.
- Node >= 22.19 (see `engines` in `package.json`); keep Dockerfile/README/scripts in sync if
  changing this — a prior review caught them drifting.
- Only `QUYCHE` and `GIAOTRINH` document types are indexed into RAG; `KHAC` is lecturer material,
  stored but not searchable (`server/api/src/documents/documents.service.ts`).
- The RAG pipeline has three independent anti-hallucination layers: calibrated confidence gate
  (τ), evidence-sufficiency grading, and post-generation groundedness verification. Don't bypass
  or merge these when touching `server/rag-service/app/pipeline/orchestrator.py`.
- E-signatures are internal (hash + audit log), not legally-binding digital certificates — the UI
  states this on every relevant page; don't imply otherwise in copy or docs.
- Approval flow is fixed in code + JSON config per form type — there is no dynamic workflow
  designer (explicitly out of scope).
- Source comments and commit messages are written in Vietnamese; match that when editing existing
  files unless told otherwise.
