# EvalHire Engine — Product History

**Repository:** [remin-franklin-eliyas/evalhire-engine](https://github.com/remin-franklin-eliyas/evalhire-engine)  
**Branch:** `main`  
**Last updated:** 2026-05-12

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

Uses the **OpenAI Python SDK** pointed at a configurable `MODEL_ENDPOINT` (defaults to any OpenAI-spec-compatible provider, e.g. GitHub AI Marketplace, Hugging Face Inference). Model: `meta-llama-3-70b-instruct`. Credentials loaded from `.env` via `python-dotenv`.

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
5. `pytest` — run all tests (with `PYTHONPATH` set to repo root)

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

---

## Staged / In-Progress Changes (as of 2026-05-12)

These changes are staged but not yet committed:

### 1. LLM Provider Migration: Anthropic → OpenAI SDK

**File:** `requirements.txt`

| Removed                  | Added               |
|--------------------------|---------------------|
| `anthropic==0.19.1`      | `openai==1.12.0`    |
| `httpx==0.27.0`          | *(removed)*         |

**Reason:** The OpenAI Python client is used as the universal SDK for OpenAI-spec-compatible providers (GitHub AI Marketplace, Hugging Face), making the integration provider-agnostic without requiring a vendor-specific SDK.

### 2. New File: `app/engine/logic.py`

Implements the core CV evaluation function `evaluate_cv(cv_text, job_description)`:
- Instantiates an `OpenAI` client with `base_url=MODEL_ENDPOINT` and `api_key=MODEL_API_KEY` from environment.
- Sends a structured prompt to the LLM asking for a Startup Fit score (0–100) and a 3-bullet critique.
- Returns the raw LLM response string.

### 3. New File: `docs/product_history.md`

This file — tracking project history, architecture, and change log.

---

## Environment Variables

Defined via `.env` (template in `.env.example`):

| Variable         | Purpose                                              |
|------------------|------------------------------------------------------|
| `MODEL_ENDPOINT` | Base URL of the OpenAI-compatible LLM API endpoint  |
| `MODEL_API_KEY`  | API key for the LLM provider                        |
