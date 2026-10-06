# AGENTS.md

Student assistant MVP for a security academy: RAG chat over regulations/curricula with
verifiable citations, class/exam schedules, quiz-based review from curricula, auto-filled
administrative forms with internal e-signatures and a two-tier approval flow, and academic
administration (faculties, classes, courses, rooms, timetable editing).

## Stack & layout

```
React/Vite (5173) ──► FastAPI (5000, prefix /api) ──┬──► PostgreSQL (5433, Docker)
                       RAG pipeline runs in-process  ├──► ChromaDB (8001, Docker)
                                                     ├──► storage/ on disk
                                                     └──► LLM: Gemini
```

- `client/` — React 19 + Vite 6 + TypeScript (strict) SPA, plain CSS in `client/src/styles/`
  (split by area: `base`, `layout`, `shell`, `chat`, `dashboard`, `study`, `staff-admin`, `polish`, then one file per feature). Three workspaces by role (`utils/roles.ts`):
  `sinh-vien` (STUDENT), `can-bo` (ACADEMIC_MANAGER / LECTURER / APPROVER / DEPARTMENT_HEAD),
  `quan-tri` (ADMIN). Shared building blocks: `PageHeader`, `Tabs`/`TabPanel`, `Breadcrumb`,
  `Metrics` in `components/shared/`.
- `server/` — FastAPI + SQLAlchemy 2 (async) + Alembic. `app/routers` (HTTP + RBAC), `app/services`
  (logic), `app/models`, `app/schemas` (Pydantic, camelCase via `CamelModel`), `app/pipeline`
  (the RAG pipeline: hybrid retrieval → rerank → abstention gate → grade/rewrite → cited generation
  → groundedness check). Entry point `server/main.py`.
- `scripts/` — Python maintenance scripts (`ingest_giaotrinh*.py`, `check_*.py`, `doc_titles.py`,
  `fix_document_titles.py`) and `scripts/test/` (HTTP acceptance tests; see below).
- `notebooks/rag-pipeline-2026.ipynb` — the research notebook the pipeline was ported from.
- `copus/` — raw source data (schedules, regulations). Not committed.

### Feature areas (server ↔ client)

| Area | Server | Client |
|---|---|---|
| Chat with citations | `chat` router/service, `pipeline/` | `ChatWorkspace`, `StudentChat`, `StaffChat` |
| Review (quiz from curricula, wrong-answer book, notes, exam plan, reminders) | `learning` router, `learning_service`, `notes_service`, `exam_plan_service`, `study_reminders` | `StudyHub`, `QuizTake`, `ReviewBook`, `Notebook` |
| Progress / lecturer insights | `progress_service`, `insights_service` (aggregate only, ≥2 learners) | `StudentHome`, `StaffHome`, `LearningInsights` |
| Schedules | `schedules` router/service, `schedule_conflicts` (class/room/lecturer clash), CSV import | `StudentSchedule`, `StaffSchedule`, `SessionForm`, `ExamForm` |
| Academic admin | `catalog` (classes, courses, students→class), `faculties`, `rooms` | `TrainingManagement` (tabs Khoa/Lớp/Môn/Học viên/Phòng) |
| Forms & approvals | `forms`, `approvals`, `signatures_service` | `Templates`, `NewSubmission`, `ApprovalInbox` |
| Accounts, audit, health | `users` router (`/admin/*`), `audit_service`, `health` | `pages/quan-tri/*` |

## Commands

```bash
cp server/.env.example server/.env   # fill in GEMINI_API_KEY; never commit .env
npm install                          # client workspace
npm run infra:up                     # PostgreSQL + ChromaDB via Docker
npm run db:migrate                   # alembic upgrade head
npm run db:seed                      # demo data (seed_phase1.py); ingest scripts depend on it

npm run dev:server                   # FastAPI on :5000  (cd server && .venv/Scripts/python main.py)
npm run dev:web                      # Vite on :5173
npm run build:web                     # tsc -b --noEmit + vite build (the type-check)
npm --prefix client run lint         # eslint
```

Python venv lives in `server/.venv` (CPU torch needs its own index URL). After a backend change
the API must be restarted; Vite hot-reloads the client.

### Tests

`scripts/test/` holds acceptance tests that talk to a running API and the Docker Postgres
(`sa-postgres-dev`). Run one with `python scripts/test/test_catalog.py`, or all with
`pwsh scripts/test/chay-tat-ca.ps1`. Login is rate-limited to 5/min per IP, so the runner sleeps
65 s between suites and you should too when running several by hand. Tests create data with a
`ZT`/`zt-` prefix and clean up after themselves (also on failure).

Demo accounts (password `Demo@2026`): `admin@`, `qldt@` (academic manager), `khoa@` (faculty head),
`gv.*@` (lecturers), `sv.*@` (students), all `@hvktcnan.edu.vn`.

## Conventions to know before editing

- Enter the app via `localhost`, not `127.0.0.1` — API CORS only allows `localhost:5173`.
- Node >= 22.19 (see `engines` in `package.json`); keep Dockerfile/README/scripts in sync if
  changing this.
- Only `QUYCHE` and `GIAOTRINH` document types are indexed into RAG; `KHAC` is lecturer material,
  stored but not searchable.
- The RAG pipeline has three independent anti-hallucination layers: calibrated confidence gate
  (τ), evidence-sufficiency grading, and post-generation groundedness verification. Don't bypass
  or merge these when touching `server/app/pipeline/orchestrator.py`. Changing the corpus requires
  recalibrating τ.
- Retrieval narrows to a single document when the question names it verbatim (accent/case
  insensitive, `Retriever.scope_documents`); the sufficiency grader reads the same 5 hits the
  generator will read. Eval set and results live in `docs/danh-gia/` — re-run `run_eval.py` after
  touching the pipeline; scoring is by keyword + manual review, one run each, so treat small
  differences as noise.
- Printed forms (`server/app/services/docx_renderer.py`) follow Nghị định 30/2020/NĐ-CP Phụ lục I (A4, margins
  20/20/30/15 mm, Times New Roman 13–14, justified body with 1 cm first-line indent and ≥ 6 pt paragraph gap,
  page numbers from page 2). "Đơn" is not one of the 29 document types in the decree, so only its general rules
  apply. When you change the layout, bump `RENDERER_VERSION`: unsigned drafts whose file carries an older stamp are
  re-rendered when opened; signed files are never re-rendered (the signature is bound to their hash).
- E-signatures are internal (hash + audit log), not legally-binding digital certificates — the UI
  states this on every relevant page; don't imply otherwise in copy or docs.
- Approval flow is fixed in code + JSON config per form type — there is no dynamic workflow
  designer (explicitly out of scope).
- Learner analytics shown to lecturers are aggregate only; never return names, codes or ids of
  individual learners from `insights_service`.
- `schedules.room` / `exam_schedules.room` are plain strings (CSV compatible); the `rooms` table is
  a catalog for choosing and capacity checks, not a foreign key. Rooms that already have a
  timetable cannot be renamed, only deactivated. "Chưa xếp…" means no room and never conflicts.
- Faculty is an entity (`faculties`); `classes.faculty` (string) is kept in sync with
  `classes.faculty_id` for older readers. A DEPARTMENT_HEAD only sees and assigns inside the
  faculty whose `head_id` is theirs (other faculties answer 404).
- Async SQLAlchemy: load relationships explicitly (`selectinload`) and read ORM attributes into
  locals before `commit()`; lazy loads raise `MissingGreenlet` (a 500).
- CSS: only existing tokens (`--ink`, `--pen`, `--gap-*`, …), dark-theme safe, no gradients,
  decorative shadows, emoji, uppercase text, coloured side borders or purple. Don't set `margin: 0`
  on a direct child of `.stack` (it cancels the vertical rhythm).
- Source comments and commit messages are written in Vietnamese; match that when editing existing
  files unless told otherwise.
