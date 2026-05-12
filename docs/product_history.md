# EvalHire Engine — Product History

**Repository:** [remin-franklin-eliyas/evalhire-engine](https://github.com/remin-franklin-eliyas/evalhire-engine)  
**Branch:** `main`  
**Last updated:** 2026-05-12

---

## Overview

EvalHire Engine is a FastAPI-based CV evaluation service with a browser UI. It accepts PDF CVs, extracts their text, and scores them against a job description using an LLM. The evaluation persona is a "Founding CTO of a high-growth AI startup", scoring candidates on **High Agency**, **Technical Depth**, and **Velocity**, returning a 0–100 "Startup Fit" score, a 3-bullet critique, and a one-sentence verdict.

---

## Architecture

```
evalhire-engine/
├── app/
│   ├── main.py              # FastAPI routes — /, /health, /evaluate, /evaluate/batch
│   ├── auth.py              # X-API-Key header authentication
│   ├── models.py            # Pydantic request/response schemas
│   ├── engine/
│   │   └── logic.py         # LLM evaluation via OpenAI-compatible client
│   ├── utils/
│   │   └── extractor.py     # PDF → text via pdfplumber
│   └── static/
│       └── index.html       # Browser UI (Single CV + Batch tabs)
├── tests/
│   └── test_main.py         # 7 tests covering all endpoints and edge cases
├── .github/workflows/
│   └── ci.yml               # GitHub Actions CI pipeline
├── .devcontainer/
│   └── devcontainer.json    # VS Code Dev Container (Python 3.10)
├── .env.example             # Environment variable template
├── .gitignore               # Excludes .env and Python artefacts
└── requirements.txt
```

### API Endpoints

| Method | Path              | Description                                                           |
|--------|-------------------|-----------------------------------------------------------------------|
| GET    | `/`               | Serves the browser UI (`app/static/index.html`)                      |
| GET    | `/health`         | Health check — `{"status": "active", "engine": "EvalHire v1.0"}`    |
| POST   | `/evaluate`       | Upload one PDF CV + JD; returns score, critique, verdict             |
| POST   | `/evaluate/batch` | Upload multiple PDF CVs + JD; returns all results ranked by score    |

### LLM Integration (`app/engine/logic.py`)

- **Provider:** GitHub Models (free tier)
- **Endpoint:** `https://models.inference.ai.azure.com`
- **Model:** `Llama-3.3-70B-Instruct`
- **Auth:** `MODEL_TOKEN` env var (`or "not-configured"` fallback so CI import doesn't crash)
- **CV truncation:** 12,000 chars before sending (~3k tokens, within Llama 3's 8k context window)
- **Temperature:** `0.1` (deterministic scoring)
- **JSON parsing:** Strips markdown code fences before `json.loads()` to handle model wrapping output in ` ```json ``` `
- **Error handling:** All exceptions raise `RuntimeError` → caught in route as `502 Bad Gateway`

### Auth (`app/auth.py`)

`X-API-Key` header checked against `API_KEY` env var. If `API_KEY` is unset, auth is silently skipped (dev/CI mode). Returns `401` on mismatch.

### Pydantic Models (`app/models.py`)

| Class              | Fields                                            |
|--------------------|---------------------------------------------------|
| `EvaluationResult` | `score: int (0–100)`, `critique: List[str]`, `verdict: str` |
| `EvaluationData`   | `filename: str`, `analysis: EvaluationResult`    |
| `EvaluationResponse` | `status: str`, `data: EvaluationData`          |
| `BatchResultItem`  | `filename`, `score`, `verdict`, `error: str|None` |
| `BatchResponse`    | `status`, `jd_preview`, `results: List[BatchResultItem]` |

### Browser UI (`app/static/index.html`)

Dark-themed single-page app served at `/`. Features:
- **Single CV tab** — drag-and-drop or click upload, paste JD, get score ring (green/amber/red), verdict, 3-bullet critique
- **Batch tab** — upload multiple PDFs, get all candidates ranked by score with colour-coded badges
- **⚙ API settings** collapsible — configurable `X-API-Key` and base URL (defaults to `window.location.origin`)

---

## Tech Stack

| Package              | Version  | Role                                    |
|----------------------|----------|-----------------------------------------|
| fastapi              | 0.110.0  | Web framework + static file serving    |
| uvicorn              | 0.27.1   | ASGI server                             |
| pdfplumber           | 0.11.0   | PDF text extraction                     |
| openai               | 1.12.0   | LLM API client (OpenAI-spec)            |
| python-dotenv        | 1.0.1    | Environment variable loading            |
| pytest               | 8.0.2    | Testing                                 |
| python-multipart     | 0.0.9    | Multipart form / file uploads           |
| httpx                | 0.27.0   | Async HTTP client (TestClient transport)|
| aiofiles             | 23.2.1   | Async file I/O (required by StaticFiles)|

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
