# EvalHire Engine — Product History

**Repository:** [remin-franklin-eliyas/evalhire-engine](https://github.com/remin-franklin-eliyas/evalhire-engine)  
**Branch:** `main`  
**Last updated:** 2026-05-14

---

## Overview

EvalHire Engine is a FastAPI-based CV evaluation service with a browser UI. It accepts PDF CVs, extracts their text, scores them against a job description using an LLM, and automatically extracts the candidate's contact details (email, phone, LinkedIn) from the CV text. Choose from **15 curated evaluator personas** (Founding CTO, YC Partner, Google L6 Engineer, Seed-stage VC, and more) or write a custom prompt. Each persona can define named evaluation dimensions (e.g. Agency, Technical Depth, Velocity) scored 0–10 by the LLM. Results include a 0–100 overall score, per-dimension scores, a 3-bullet critique, a one-sentence verdict, a percentile rank, and a contact card. The `/compare` endpoint ranks 2–10 candidates head-to-head in a single authenticated request.

---

## Architecture

```
evalhire-engine/
├── app/
│   ├── main.py              # FastAPI routes — /, /app, /health, /evaluate, /evaluate/batch, /compare, /auth/*, /history, /personas
│   ├── auth.py              # JWT + X-API-Key auth, bcrypt password hashing, get_optional_user / get_current_user deps
│   ├── database.py          # SQLAlchemy engine + session factory (SQLite locally, PostgreSQL on Railway)
│   ├── db_models.py         # ORM models: User, EvaluationRecord, Persona
│   ├── models.py            # Pydantic request/response schemas
│   ├── routers/
│   │   ├── auth_routes.py   # POST /auth/register, /auth/login, GET /auth/me, DELETE /auth/me
│   │   ├── history_routes.py# GET /history (paginated), POST /history/purge
│   │   └── persona_routes.py# GET /personas, GET /personas/{id}, POST /personas
│   ├── engine/
│   │   ├── logic.py         # LLM evaluation (multi-provider: GitHub Models / OpenAI / Anthropic)
│   │   └── personas_seed.py # 15 curated system personas — seeded on startup
│   ├── utils/
│   │   └── extractor.py     # PDF → text + contact info regex extraction
│   └── static/
│       ├── landing.html     # Marketing landing page (served at /)
│       └── index.html       # Browser app — Single CV + Batch + Compare + History tabs (served at /app)
├── tests/
│   ├── test_main.py         # Core endpoint tests
│   └── test_personas.py     # 15 Phase 1 tests covering /personas and /compare
├── .github/workflows/
│   └── ci.yml               # GitHub Actions CI pipeline
├── .devcontainer/
│   └── devcontainer.json    # VS Code Dev Container (Python 3.10)
├── .env.example             # Environment variable template
├── .gitignore               # Excludes .env and Python artefacts
└── requirements.txt
```

### API Endpoints

| Method | Path                 | Auth                | Description                                                                                            |
|--------|----------------------|---------------------|--------------------------------------------------------------------------------------------------------|
| GET    | `/`                  | None                | Serves the marketing landing page (`app/static/landing.html`)                                         |
| GET    | `/app`               | None                | Serves the browser app (`app/static/index.html`)                                                      |
| GET    | `/health`            | None                | Health check                                                                                           |
| POST   | `/auth/register`     | None                | Create account; returns JWT                                                                            |
| POST   | `/auth/login`        | None                | Sign in; returns JWT                                                                                   |
| GET    | `/auth/me`           | Bearer JWT          | Returns current user                                                                                   |
| DELETE | `/auth/me`           | Bearer JWT          | Permanently deletes the account and all associated history                                             |
| GET    | `/history`           | Bearer JWT          | Returns user's evaluations paginated (`skip`, `limit`); newest first                                  |
| POST   | `/history/purge`     | Bearer JWT          | Deletes all history records for the user; returns `{ "deleted": N }`                                  |
| POST   | `/evaluate`          | X-API-Key OR Bearer | Upload one PDF CV + JD; returns score, dimensions, percentile, critique, verdict, contact. Saves to history if Bearer present. |
| POST   | `/evaluate/batch`    | X-API-Key OR Bearer | Upload multiple PDF CVs + JD; returns all results ranked by score. Saves to history if Bearer present. |
| GET    | `/personas`          | None                | List all public personas sorted by `use_count` desc; paginated                                        |
| GET    | `/personas/{id}`     | None                | Get a single public persona by ID                                                                      |
| POST   | `/personas`          | Bearer JWT          | Create a custom persona; returns `PersonaResponse`                                                     |
| POST   | `/compare`           | Bearer JWT          | Evaluate and rank 2–10 CVs in one request; returns sorted results with per-candidate dimensions. Does not write to history. |
| GET    | `/history`           | Bearer JWT     | Returns user's last 200 evaluations, newest first                 |
| POST   | `/evaluate`          | X-API-Key OR Bearer | Upload one PDF CV + JD; returns score, critique, verdict, contact. Saves to history if Bearer token present. |
| POST   | `/evaluate/batch`    | X-API-Key OR Bearer | Upload multiple PDF CVs + JD; returns all results ranked by score. Saves to history if Bearer token present. |

### LLM Integration (`app/engine/logic.py`)

- **Provider:** Configurable via `MODEL_PROVIDER` env var:
  - `github` (default) — Llama 3.3 70B Instruct at `https://models.inference.ai.azure.com`
  - `openai` — GPT-4o at `https://api.openai.com/v1`
  - `anthropic` — Claude 3.5 Sonnet at `https://api.anthropic.com/v1`
- **Auth:** `MODEL_TOKEN` env var (`or "not-configured"` fallback so CI import doesn't crash)
- **CV truncation:** 12,000 chars before sending (~3k tokens, within Llama 3's 8k context window)
- **Temperature:** `0.1` (deterministic scoring)
- **Dimension scoring:** When `dimension_names` is passed, the system prompt includes a `"dimensions"` key in the JSON schema with the persona's named axes (each scored 0–10).
- **JSON parsing:** Strips markdown code fences before `json.loads()` to handle model wrapping output in ` ```json ``` `
- **Error handling:** All exceptions raise `RuntimeError` → caught in route as `502 Bad Gateway`

### Auth (`app/auth.py`)

Two authentication mechanisms coexist:

- **X-API-Key** (`verify_api_key` dependency): checked against `API_KEY` env var. Skipped if `API_KEY` unset (dev/CI mode). Used by `/evaluate` and `/evaluate/batch` for backward-compatible CLI/API access.
- **JWT Bearer** (`get_optional_user` / `get_current_user` dependencies): HS256 tokens signed with `SECRET_KEY` (auto-generated if unset), 30-day expiry. Password hashing uses `bcrypt` directly (not `passlib` — see bug fix below).

The `/evaluate` and `/evaluate/batch` routes accept either auth method. If a valid JWT Bearer token is present, the evaluation is saved to the database. `/history` and `/auth/me` require JWT Bearer only.

### Database (`app/database.py`, `app/db_models.py`)

- **Engine:** SQLAlchemy 2.0, sync sessions.
- **Local:** SQLite (`evalhire.db` in repo root — gitignored).
- **Production:** PostgreSQL via `DATABASE_URL` env var (Railway). `postgres://` prefix auto-converted to `postgresql://`.
- **Tables created** automatically on app startup via `Base.metadata.create_all()`.

**ORM Models:**

| Model              | Key columns                                                                                                                                                                                           |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `User`             | `id`, `email` (unique), `hashed_password`, `tier` (`free`/`pro`), `created_at`                                                                                                                       |
| `Persona`          | `id`, `name`, `description`, `prompt`, `dimensions` (JSON string), `author_id` (FK, null = system persona), `is_public`, `is_system`, `use_count`, `created_at`                                      |
| `EvaluationRecord` | `id`, `user_id` (FK), `created_at`, `filename`, `jd_preview`, `score`, `verdict`, `critique_json`, `persona_used`, `persona_id` (FK), `dimensions_json`, `percentile`, `contact_email`, `contact_phone`, `contact_linkedin` |

### Pydantic Models (`app/models.py`)

| Class                | Fields                                                                                                                            |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `ContactInfo`        | `email: str\|None`, `phone: str\|None`, `linkedin: str\|None`                                                                     |
| `EvaluationResult`   | `score: int (0–100)`, `critique: List[str]`, `verdict: str`, `dimensions: Dict[str, int] = {}`                                   |
| `EvaluationData`     | `filename: str`, `analysis: EvaluationResult`, `contact: ContactInfo\|None`                                                       |
| `EvaluationResponse` | `status: str`, `data: EvaluationData`, `percentile: int\|None`                                                                    |
| `BatchResultItem`    | `filename`, `score`, `verdict`, `error: str\|None`, `contact: ContactInfo\|None`                                                  |
| `BatchResponse`      | `status`, `jd_preview`, `results: List[BatchResultItem]`                                                                          |
| `PersonaCreate`      | `name: str`, `description: str\|None`, `prompt: str`, `dimensions: List[str] = []`, `is_public: bool = True`                     |
| `PersonaResponse`    | `id`, `name`, `description`, `prompt`, `dimensions`, `is_public`, `is_system`, `author_id`, `use_count`, `created_at`            |
| `CompareResultItem`  | `filename`, `score`, `verdict`, `dimensions: Dict[str, int] = {}`, `contact: ContactInfo\|None`, `error: str\|None`              |
| `CompareResponse`    | `status`, `jd_preview`, `persona_name: str\|None`, `results: List[CompareResultItem]`                                            |

### Browser UI (`app/static/index.html` and `app/static/landing.html`)

**Landing page** (`/`) — Dark-themed marketing page with hero section, "Persona Marketplace" / "Dimension scoring" / "Candidate comparison" feature cards, demo result card with dimension score bars and "Top 8%" percentile line, all 15 persona pills + Custom, footer, and a privacy modal.

**App** (`/app`) — Dark-themed single-page app. Features:
- **Single CV tab** — drag-and-drop or click upload, paste JD, get score ring, verdict, 3-bullet critique, dimension score bars, percentile badge, and "Reach out" contact card
- **Batch tab** — upload multiple PDFs, get all candidates ranked by score with contact links per row
- **Compare tab** — upload 2–10 PDFs (requires sign-in), sends to `POST /compare`, renders ranked cards with per-candidate dimension bars
- **History tab** — paginated via `GET /history`; each row shows dimension tag chips and percentile badge inline; click to expand full critique and contact links
- **Sign in / Create account modal** — email + password; JWT stored in `localStorage`; account pill shows logged-in email with sign-out
- **Persona chips** — dynamically loaded from `GET /personas` on page load; clicking a system persona sends `persona_id`; Custom chip sends raw text
- **⚙ API settings** collapsible — configurable `X-API-Key` and base URL
- **Bearer token** sent automatically on all API calls when logged in

---

## Tech Stack

| Package                   | Version  | Role                                          |
|---------------------------|----------|-----------------------------------------------|
| fastapi                   | 0.110.0  | Web framework + static file serving           |
| uvicorn                   | 0.27.1   | ASGI server                                   |
| pdfplumber                | 0.11.0   | PDF text extraction                           |
| openai                    | 1.12.0   | LLM API client (OpenAI-spec)                  |
| python-dotenv             | 1.0.1    | Environment variable loading                  |
| pytest                    | 8.0.2    | Testing                                       |
| python-multipart          | 0.0.9    | Multipart form / file uploads                 |
| httpx                     | 0.27.0   | Async HTTP client (TestClient transport)      |
| aiofiles                  | 23.2.1   | Async file I/O (required by StaticFiles)      |
| sqlalchemy                | 2.0.28   | ORM + database sessions                       |
| python-jose[cryptography] | 3.3.0    | JWT creation and validation                   |
| bcrypt                    | 4.1.3    | Password hashing (replaces passlib)           |
| email-validator           | 2.1.1    | Pydantic `EmailStr` validation                |

---

## CI/CD — GitHub Actions

**Workflow file:** `.github/workflows/ci.yml`  
**Name:** EvalHire CI  
**Triggers:** `push`, `pull_request` (all branches)

### Pipeline Steps

1. `actions/checkout@v4` — check out source
2. `actions/setup-python@v5` — Python 3.10
3. `actions/cache@v3` — cache `~/.cache/pip` keyed on `requirements.txt` hash
4. `pip install -r requirements.txt` — install dependencies
5. `pytest` — run all 7 tests (`PYTHONPATH` set to repo root; `MODEL_TOKEN` injected from `secrets.MODEL_TOKEN`)

**Runner:** `ubuntu-latest`

---

## Dev Container

**Config:** `.devcontainer/devcontainer.json`  
**Base image:** `mcr.microsoft.com/devcontainers/python:3.10`  
**Port forwarded:** `8000`  
**Post-create command:** `pip install --upgrade pip && pip install -r requirements.txt`

VS Code extensions pre-installed:
- `ms-python.python`, `ms-python.vscode-pylance`, `njpwerner.autodocstring`, `charliermarsh.ruff`

---

## Security Incident — 2026-05-12

### What happened

A real **GitHub Personal Access Token** was accidentally committed to `.env` (commit `e52add3`) and a second token was placed in `.env.example` (commit `a041e65`). Both pushes were blocked by GitHub Push Protection.

### Remediation

1. Both tokens **revoked** on GitHub.
2. `.env` cleared — replaced with placeholder values.
3. `.env.example` amended — real token replaced with `ghp_your_github_models_token_here`.
4. Root `.gitignore` created — `.env` permanently excluded from tracking.
5. `git filter-branch` rewrote history to remove `.env` from all prior commits.
6. `git push --force` applied on both occasions.

### Lessons

- `.env` is gitignored at repo root — can never be committed again.
- `.env.example` must only ever contain placeholder values.
- CI injects secrets at runtime via `secrets.MODEL_TOKEN` — no file-based secrets in the repo.

---

## Commit History

All commits by **Remin Franklin Eliyas** (`remin-franklin-eliyas`).

| Hash      | Date       | Message |
|-----------|------------|---------|
| `f43074f` | 2026-05-12 | *(clone — empty repo)* |
| `5bca7f9` | 2026-05-12 | Add initial project files |
| `d4449f8` | 2026-05-12 | Add devcontainer, CI workflow, main app logic, PDF extractor, initial tests |
| `b6c8003` | 2026-05-12 | Set PYTHONPATH in CI; add `__init__.py` files |
| `43451a2` | 2026-05-12 | Add python-multipart to requirements |
| `57413fa` | 2026-05-12 | Implement CV evaluation logic; add product history docs |
| `44b3efc` | 2026-05-12 | Update requirements; improve test context manager |
| `e52add3` | 2026-05-12 | ⚠️ Add .env with GITHUB_TOKEN *(secret leak — no longer on remote)* |
| `0eb7cc1` | 2026-05-12 | Add env vars to .env; create .gitignore |
| `7a8c756` | 2026-05-12 | *(filter-branch rewrite — .env scrubbed from history)* |
| `d417706` | 2026-05-12 | Add MODEL_TOKEN to CI; enhance CV evaluation logic |
| `023a522` | 2026-05-12 | Update product history docs |
| `ba171e6` | 2026-05-12 | Refactor /evaluate endpoint; handle PDF extraction errors |
| `7787d81` | 2026-05-12 | Return structured JSON from LLM; improve error handling |
| `c94cc07` | 2026-05-12 | Add FastAPI app init and /health endpoint |
| `d5ce503` | 2026-05-12 | Implement API key auth; add Pydantic response models |
| `c2157be` | 2026-05-12 | Fix auth to handle missing API_KEY gracefully |
| `ca24551` | 2026-05-12 | Fix mock patch paths in tests |
| `3aa5df8` | 2026-05-12 | Add /evaluate/batch endpoint; expand test suite to 7 tests |
| `a041e65` | 2026-05-12 | ⚠️ Add real token to .env.example *(secret leak — amended)* |
| `6d877b0` | 2026-05-12 | Amend: replace real token in .env.example with placeholder |
| `9b5dde1` | 2026-05-12 | Add browser UI (static HTML); move health check to /health; add aiofiles; JSON fence-stripping in logic.py |

---

## Change Log

### 2026-05-16 — Phase 1: Persona Marketplace, Dimension Scoring, Percentile Ranking, Candidate Comparison

#### Persona Marketplace

- **`app/db_models.py`**: New `Persona` ORM model (`id`, `name`, `description`, `prompt`, `dimensions` JSON string, `author_id` FK nullable — null = system persona, `is_public`, `is_system`, `use_count`, `created_at`). `User` gains a `personas` relationship with cascade delete. `EvaluationRecord` gains `persona_id` FK, `dimensions_json`, and `percentile` columns. Three new `ALTER TABLE` inline migrations run idempotently on startup.
- **`app/engine/personas_seed.py`** (new): 15 curated system personas, each with name, description, prompt, and 3 dimension names. `seed_system_personas(db)` is idempotent — checks by name, inserts only missing rows. Called on every startup.
- **`app/routers/persona_routes.py`** (new): `GET /personas` (sorted by `use_count` desc, paginated), `GET /personas/{id}` (404 if not found or not public), `POST /personas` (requires Bearer auth, validates name + prompt).
- **`app/main.py`**: `_resolve_persona(persona_id, persona_text, db)` helper resolves to `(prompt, dimension_names, persona_obj | None)`. `_compute_percentile(persona_id, score, db)` returns the candidate's percentile rank once ≥5 records exist for that persona, else `None`. `/evaluate` now accepts `persona_id` form field; increments `use_count`; saves `persona_id`, `dimensions_json`, and `percentile` to `EvaluationRecord`.

#### Dimension Scoring

- **`app/engine/logic.py`**: `_build_system_prompt` now accepts an optional `dimension_names` list and appends a `"dimensions"` key to the LLM JSON schema instruction with the persona-specific axis names. `evaluate_cv()` passes `dimension_names` through; result always contains a `dimensions: {}` key.
- **`app/models.py`**: `EvaluationResult.dimensions: Dict[str, int] = {}`. `EvaluationResponse.percentile: int | None = None`. New `PersonaCreate`, `PersonaResponse`, `CompareResultItem`, `CompareResponse` schemas added.

#### Candidate Comparison Mode

- **`app/main.py`**: New `POST /compare` endpoint. Requires Bearer auth. Accepts 2–10 PDF files + JD + optional `persona` / `persona_id`. Processes all CVs synchronously; skips non-PDFs with error. Returns `CompareResponse` sorted by score desc. Increments persona `use_count` by number of successful evals. Does **not** write to evaluation history.

#### UI Updates

- **`app/static/landing.html`**: Stats updated to "15+ curated personas". Feature cards replaced with Persona Marketplace / Dimension scoring / Candidate comparison. Demo result card now shows persona tag, dimension score bars (Agency 9, Technical Depth 8, Velocity 7), and "Top 8%" percentile line. All 15 persona pills displayed in the personas section.
- **`app/static/index.html`**: Compare tab added (auth-gated). Persona chips now loaded dynamically from `GET /personas` on page load — clicking a system persona sends `persona_id` instead of raw text. `renderSingle` shows percentile badge + dimension bars. `renderCompare` renders ranked cards with dimensions. History rows show dimension chips and percentile badge.

#### Tests

- **`tests/test_personas.py`** (new): 15 tests covering `GET /personas` (list, pagination), `POST /personas` (success, auth required, validation), `GET /personas/{id}` (success, 404), `/evaluate` with `persona_id` (use_count increment, dimensions in history response, 404 for invalid id), `/compare` (auth required, min 2 files, response shape + score sorting, with `persona_id`, non-PDF skipping).

---

### 2026-05-14 — Phase 0: Rate Limits, Multi-provider LLM, Async Batch, Account Deletion, History Purge, Pagination

#### Rate Limiting

- **`app/main.py`**: `FREE_TIER_MONTHLY_LIMIT` env var (default `20`). `/evaluate` and `/evaluate/batch` check the authenticated user's call count for the current calendar month against the limit. Exceeding it returns `429 Too Many Requests`.
- **`app/db_models.py`**: `User` gains a `tier TEXT NOT NULL DEFAULT 'free'` column via inline `ALTER TABLE` migration on startup.

#### Multi-provider LLM

- **`app/engine/logic.py`**: `MODEL_PROVIDER` env var switches between `github` (default — Llama 3.3 70B via `https://models.inference.ai.azure.com`), `openai` (GPT-4o via `https://api.openai.com/v1`), and `anthropic` (Claude 3.5 Sonnet via `https://api.anthropic.com/v1`). All three use the OpenAI Python SDK with provider-specific `base_url` and model name.

#### Async Batch with Job Polling

- **`app/main.py`**: `/evaluate/batch` now processes CVs concurrently via `asyncio.gather`, bounded by a semaphore to avoid overwhelming the LLM API. Aggregate upload size is capped — oversized requests return `413`.

#### Account Deletion + History Purge

- **`app/routers/auth_routes.py`**: `DELETE /auth/me` — deletes the authenticated user and all associated `EvaluationRecord` rows (cascade). Returns `204 No Content`.
- **`app/routers/history_routes.py`**: `POST /history/purge` — deletes all `EvaluationRecord` rows for the authenticated user; returns `{ "deleted": N }`.

#### Paginated History

- **`app/routers/history_routes.py`**: `GET /history` now accepts `skip: int = 0` and `limit: int = 50` query parameters (max `limit` capped at `200`). Previously returned a fixed last-200 slice.

#### Test Updates

- **`tests/test_main.py`**: Updated to cover Phase 0 changes including rate limit responses and paginated history.

---

### 2026-05-14 — Accounts, History, Landing Page + bcrypt Fix

#### User Accounts + JWT Auth

- **`app/auth.py`**: Extended with JWT support. `create_access_token(user_id)` issues 30-day HS256 tokens. `get_optional_user` returns the logged-in `User` or `None`. `get_current_user` raises `401` if no valid token. `hash_password` / `verify_password` use `bcrypt` directly (dropped `passlib` — see below).
- **`app/database.py`** (new): SQLAlchemy engine + `SessionLocal` + `Base`. SQLite locally, PostgreSQL on Railway via `DATABASE_URL`. `postgres://` → `postgresql://` auto-fix.
- **`app/db_models.py`** (new): `User` ORM model (id, email, hashed_password, created_at). `EvaluationRecord` ORM model (id, user_id FK, created_at, filename, jd_preview, score, verdict, critique_json, persona_used, contact_email/phone/linkedin).
- **`app/routers/auth_routes.py`** (new): `POST /auth/register` (creates user, returns JWT), `POST /auth/login` (validates credentials, returns JWT), `GET /auth/me` (returns current user).
- **`app/main.py`**: `Base.metadata.create_all()` on startup. Routers included. Both evaluate routes now accept optional Bearer token and save `EvaluationRecord` to DB when logged in.

#### Evaluation History

- **`app/routers/history_routes.py`** (new): `GET /history` returns last 200 `EvaluationRecord` rows for the authenticated user, ordered newest first.
- **`app/static/index.html`**: History tab added. Loads `/history` on tab switch. Shows score ring, filename, date, verdict, expandable critique, and contact links per row. Shows login prompt if unauthenticated.

#### Landing Page

- **`app/static/landing.html`** (new): Full dark-themed marketing page. Hero with tagline, 6 feature cards, example result card, persona pills, footer with privacy modal.
- **`app/main.py`**: `GET /` now serves `landing.html`. `GET /app` serves `index.html` (app moved from `/` to `/app`).
- **`app/static/index.html`**: Auth modal (sign in / create account), account pill in header with sign-out, Bearer token sent on all API calls when logged in.

#### Bug Fix — passlib + bcrypt 4.x incompatibility

`passlib 1.7.4` is unmaintained and fails with `bcrypt 4.x` due to removal of `bcrypt.__about__`. Replaced `passlib.context.CryptContext` with direct `bcrypt.hashpw` / `bcrypt.checkpw` calls. `passlib[bcrypt]` removed from `requirements.txt`; pinned `bcrypt==4.1.3`.

---

### 2026-05-14 — Configurable Persona + Contact Info Extraction

#### Configurable Evaluator Persona

- **`app/engine/logic.py`**: `DEFAULT_PERSONA` constant extracted (Founding CTO). New `_build_system_prompt(persona)` injects persona into the LLM system message while always appending the JSON schema instruction. `evaluate_cv()` now accepts an optional `persona` argument.
- **`app/main.py`**: Both `/evaluate` and `/evaluate/batch` accept an optional `persona` form field. Empty/missing value falls back to `DEFAULT_PERSONA`.
- **`app/static/index.html`**: Persona textarea added below JD field in both tabs. Five preset chips (Founding CTO, VP Sales, Design Lead, Head of Growth, Clinical Lead) and a Custom chip. Clicking a preset fills and locks the textarea; Custom clears it for free text. Persona is appended to the `FormData` on submit.

#### Contact Info Extraction

- **`app/models.py`**: New `ContactInfo(email, phone, linkedin)` Pydantic model. Optional `contact: ContactInfo | None` field added to `EvaluationData` and `BatchResultItem`.
- **`app/utils/extractor.py`**: New `extract_contact_info(text: str) -> ContactInfo` using three regex patterns — RFC-safe email, permissive international phone (covers +44, +1, 07xxx), and LinkedIn handle (normalised to canonical URL). No LLM call — pure regex, zero added latency.
- **`app/main.py`**: Both routes call `extract_contact_info(extracted_text)` after PDF extraction and include the result in the response.
- **`app/static/index.html`**: `buildContactCard(c)` renders a dark "Reach out" card for single results with `mailto:`, `tel:`, and LinkedIn links. `buildBatchContact(c)` renders compact inline links on each batch row. Cards are hidden when no contact info is found.

#### Bug Fix

- **`app/main.py`**: Fixed `IndentationError` in `/evaluate/batch` — `for upload in files:` loop header was dropped during an earlier multi-replace, causing the server to crash on startup. Also fixed a missing `results = []` initialisation that caused a `NameError` in the same route.

---

### 2026-05-12 — Browser UI + Final Hardening (`9b5dde1`)

- **`app/static/index.html`** (new): full dark-themed browser UI with Single CV and Batch tabs, drag-and-drop, score ring, and configurable API settings panel
- **`app/main.py`**: `/` now serves `index.html` via `FileResponse`; `/health` is the new health check; CORS middleware added; `StaticFiles` mounted at `/static`; 10 MB upload limit on both `/evaluate` and `/evaluate/batch`
- **`app/engine/logic.py`**: markdown fence-stripping before `json.loads()`; empty response check; model updated to `Llama-3.3-70B-Instruct`
- **`requirements.txt`**: `aiofiles==23.2.1` added (required by `StaticFiles`)
- **`tests/test_main.py`**: health check test updated to `/health`

### 2026-05-12 — Batch Endpoint + Full Test Suite (`3aa5df8`)

- **`POST /evaluate/batch`**: accepts N PDFs + one JD; processes each independently; skips bad files with error field; returns results sorted descending by score
- **`app/models.py`**: `BatchResultItem` and `BatchResponse` Pydantic models added
- **`tests/test_main.py`**: 7 tests total — health check, non-PDF rejection, wrong API key (401), correct API key (200), response shape, batch shape, batch skip-non-PDF

### 2026-05-12 — Auth, Pydantic Models, Hardening (`d5ce503` → `c2157be`)

- **`app/auth.py`** (new): `verify_api_key` FastAPI dependency; skips auth if `API_KEY` unset
- **`app/models.py`** (new): `EvaluationResult`, `EvaluationData`, `EvaluationResponse`
- **`app/main.py`**: `response_model=EvaluationResponse`; `Depends(verify_api_key)`; validates LLM output via Pydantic; malformed LLM response → `500`
- **LLM error path**: `raise RuntimeError` instead of silently returning `score: 0`; caught in route as `502`
- **`app/engine/logic.py`**: `api_key=os.getenv("MODEL_TOKEN") or "not-configured"` — prevents import crash in CI when secret is unset; CV text truncated to 12,000 chars; `response_format` removed (not supported by GitHub Models/Llama 3); CORS middleware added

### 2026-05-12 — Core Pipeline (`d4449f8` → `7787d81`)

- FastAPI app with `/evaluate` (PDF upload + JD form field)
- `pdfplumber`-based PDF text extraction
- OpenAI SDK client → GitHub Models → Llama 3 structured JSON response
- CI pipeline: `pytest` with `PYTHONPATH` and `MODEL_TOKEN` from secrets

---

## Environment Variables

Defined via `.env` (gitignored — never commit):

| Variable      | Required | Purpose                                                          |
|---------------|----------|------------------------------------------------------------------|
| `MODEL_TOKEN` | Yes      | GitHub Models API key (passed to OpenAI client)                 |
| `API_KEY`     | No       | Protects endpoints via `X-API-Key` header; unset = auth disabled |

> In CI, `MODEL_TOKEN` is set via `secrets.MODEL_TOKEN`. No `.env` file exists on the runner.


---

## Overview

EvalHire Engine is a FastAPI-based CV evaluation service. It accepts PDF CVs, extracts their text, and scores them against a job description using an LLM. The evaluation persona is a "Founding CTO of a high-growth AI startup", scoring candidates on **High Agency**, **Technical Depth**, and **Velocity**, returning a 0–100 "Startup Fit" score and a 3-bullet critique.

---

## Architecture

```
evalhire-engine/
├── app/
│   ├── main.py              # FastAPI app — /  (health) and /extract (PDF upload)
│   ├── engine/
│   │   └── logic.py         # LLM evaluation via OpenAI-compatible client
│   └── utils/
│       └── extractor.py     # PDF → text via pdfplumber
├── tests/
│   └── test_main.py         # Health-check integration test
├── .github/workflows/
│   └── ci.yml               # GitHub Actions CI pipeline
├── .devcontainer/
│   └── devcontainer.json    # VS Code Dev Container (Python 3.10)
├── .env.example             # Environment variable template
└── requirements.txt
```

### API Endpoints

| Method | Path       | Description                                              |
|--------|------------|----------------------------------------------------------|
| GET    | `/`        | Health check — returns `{"status": "active", "engine": "EvalHire v1.0"}` |
| POST   | `/extract` | Upload a PDF CV; returns filename + first 500 chars of extracted text |

### LLM Integration (`app/engine/logic.py`)

Uses the **OpenAI Python SDK** with the endpoint hardcoded to `https://models.inference.ai.azure.com` (GitHub Models free tier). Model: `meta-llama-3-70b-instruct`, temperature `0.1`. Uses a system/user message split — system prompt sets the CTO persona, user message injects the JD and CV. API key read from `MODEL_TOKEN` env var. Errors caught and returned as a string.

---

## Tech Stack

| Package              | Version  | Role                          |
|----------------------|----------|-------------------------------|
| fastapi              | 0.110.0  | Web framework                 |
| uvicorn              | 0.27.1   | ASGI server                   |
| pdfplumber           | 0.11.0   | PDF text extraction           |
| openai               | 1.12.0   | LLM API client (OpenAI-spec)  |
| python-dotenv        | 1.0.1    | Environment variable loading  |
| pytest               | 8.0.2    | Testing                       |
| python-multipart     | 0.0.9    | Multipart form / file uploads |
| httpx                | 0.27.0   | Async HTTP client (test transport) |

---

## CI/CD — GitHub Actions

**Workflow file:** `.github/workflows/ci.yml`  
**Name:** EvalHire CI  
**Triggers:** `push`, `pull_request` (all branches)

### Pipeline Steps

1. `actions/checkout@v4` — check out source
2. `actions/setup-python@v5` — Python 3.10
3. `actions/cache@v3` — cache `~/.cache/pip` keyed on `requirements.txt` hash
4. `pip install -r requirements.txt` — install dependencies
5. `pytest` — run all tests (with `PYTHONPATH` set to repo root; `MODEL_TOKEN` injected from `secrets.MODEL_TOKEN`)

**Runner:** `ubuntu-latest`

---

## Dev Container

**Config:** `.devcontainer/devcontainer.json`  
**Base image:** `mcr.microsoft.com/devcontainers/python:3.10`  
**Port forwarded:** `8000`  
**Post-create command:** `pip install --upgrade pip && pip install -r requirements.txt`

VS Code extensions pre-installed in the container:
- `ms-python.python`
- `ms-python.vscode-pylance`
- `njpwerner.autodocstring`
- `charliermarsh.ruff`

---

## Commit History

All commits are by **Remin Franklin Eliyas** (`remin-franklin-eliyas`).

| Hash      | Date       | Message                                                                                                      |
|-----------|------------|--------------------------------------------------------------------------------------------------------------|
| `f43074f` | 2026-05-12 | *(Initial state cloned from origin — empty repo)*                                                            |
| `5bca7f9` | 2026-05-12 | Add initial project files including .env.example, CI configuration, .gitignore, main.py, requirements.txt, and test .gitignore |
| `d4449f8` | 2026-05-12 | Add devcontainer configuration, CI workflow, main application logic, PDF extraction utility, and initial tests |
| `b6c8003` | 2026-05-12 | Set PYTHONPATH in CI workflow and add empty `__init__.py` files for app and utils modules                    |
| `43451a2` | 2026-05-12 | Add python-multipart to requirements.txt                                                                     |
| `57413fa` | 2026-05-12 | Implement CV evaluation logic using OpenAI SDK and add product history documentation                         |
| `44b3efc` | 2026-05-12 | Update requirements and improve test initialization with context manager                                     |
| `e52add3` | 2026-05-12 | ⚠️ Add .env file with GITHUB_TOKEN *(secret leak — history-rewritten, this commit no longer on remote)*     |
| `0eb7cc1` | 2026-05-12 | Add environment variables to .env file and create .gitignore for sensitive data                              |
| `7a8c756` | 2026-05-12 | *(filter-branch rewrite — scrubbed `.env` from all prior commits)*                                           |
| `d417706` | 2026-05-12 | Update CI workflow to include MODEL_TOKEN environment variable and enhance CV evaluation logic                |

---

## Security Incident — 2026-05-12

### What happened

A real **GitHub Personal Access Token** was accidentally committed to `.env` in commit `e52add3` and a push to `origin/main` was attempted. GitHub Push Protection blocked the push and flagged the secret at `.env:1`.

### Remediation steps taken

1. **Token revoked** on GitHub (Settings → Developer settings → Personal access tokens).
2. **`.env` cleared** — token replaced with placeholder `your_token_here`.
3. **Root `.gitignore` created** — `.env` added so it can never be tracked again.
4. **History rewritten** — `git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch .env'` removed `.env` from every commit.
5. **Force-pushed** — `git push origin main --force` succeeded; the secret no longer exists in remote history.

### Lessons applied

- `.env` is now gitignored at the repo root.
- `.env.example` was removed; environment setup is documented in the **Environment Variables** section below.
- CI now uses `secrets.MODEL_TOKEN` injected at runtime rather than any file-based secret.

---

## Change Log

### 2026-05-12 — CV Evaluation Logic & CI Hardening (`57413fa` → `d417706`)

**`app/engine/logic.py`** (enhanced from initial stub):
- Endpoint hardcoded to `https://models.inference.ai.azure.com` (GitHub Models).
- API key env var renamed `MODEL_API_KEY` → `MODEL_TOKEN` to match GitHub Models convention.
- Prompt restructured to system + user message split (system: CTO persona, user: JD + CV).
- Temperature lowered `0.7` → `0.1` for more deterministic scoring.
- Added `try/except` — errors returned as `"Brain Error: <msg>"`.

**`tests/test_main.py`** (hardened):
- `TestClient` now used as a context manager (`with TestClient(app) as client`) for correct lifespan handling.

**`requirements.txt`** (finalised):
- `httpx==0.27.0` added back (required as async transport for `TestClient`).
- Final dependency set: `fastapi`, `uvicorn`, `pdfplumber`, `openai`, `python-dotenv`, `pytest`, `python-multipart`, `httpx`.

**`.github/workflows/ci.yml`** (updated):
- `MODEL_TOKEN` now injected from `secrets.MODEL_TOKEN` into the `pytest` step so tests run with a valid token in CI.

---

## Environment Variables

Defined via `.env` (gitignored — never commit this file):

| Variable         | Purpose                                                       |
|------------------|---------------------------------------------------------------|
| `GITHUB_TOKEN`   | GitHub PAT — used for GitHub Models API access (local only)  |
| `MODEL_TOKEN`    | API key passed to the OpenAI client (`logic.py` + CI secret) |
| `MODEL_ENDPOINT` | *(legacy)* Base URL — now hardcoded in `logic.py`            |

> In CI, `MODEL_TOKEN` is set via a GitHub Actions repository secret (`secrets.MODEL_TOKEN`). No `.env` file is present on the runner.
