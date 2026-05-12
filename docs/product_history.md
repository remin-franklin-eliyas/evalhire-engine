# EvalHire Engine — Product History

**Repository:** [remin-franklin-eliyas/evalhire-engine](https://github.com/remin-franklin-eliyas/evalhire-engine)  
**Branch:** `main`  
**Last updated:** 2026-05-12 (post-security-remediation)

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
