# EvalHire Engine

An AI-powered CV screening API built to replace the broken parts of hiring. Upload a PDF CV and a job description — get back a structured score, per-dimension scores, critique, hire/no-hire verdict, and the candidate's contact details (email, phone, LinkedIn) so you can reach out directly. Choose from **15 curated evaluator personas** (Founding CTO, YC Partner, Google L6 Engineer, Seed-stage VC, and more), compare 2–10 candidates head-to-head with a single `/compare` call, or write your own custom persona.

---

## How it works

1. You `POST` a candidate's PDF CV + a job description to `/evaluate`
2. The engine extracts the CV text from the PDF and parses contact info (email, phone, LinkedIn)
3. It sends both to the configured LLM (GitHub Models Llama 3 70B by default; switchable to OpenAI or Anthropic via `MODEL_PROVIDER`) using the chosen evaluator persona — pick from 15 curated presets or supply your own prompt
4. Returns a structured JSON evaluation scored 0–100 with per-dimension scores (e.g. Agency: 9, Technical Depth: 8), a 3-bullet critique, verdict, contact details, and a percentile rank among all CVs evaluated under the same persona
5. Use `/compare` to rank 2–10 candidates side-by-side in a single authenticated request

---

## Quickstart

### Prerequisites

- Python 3.10+
- A [GitHub Models](https://github.com/marketplace/models) API token

### Local setup

```bash
git clone https://github.com/remin-franklin-eliyas/evalhire-engine.git
cd evalhire-engine

pip install -r requirements.txt

# Create your .env file (never commit this)
echo "MODEL_TOKEN=your_github_models_token_here" > .env

uvicorn app.main:app --reload
```

The API will be running at `http://localhost:8000`.

**Landing page:** `http://localhost:8000` — marketing page with feature overview and privacy statement.

**App UI:** `http://localhost:8000/app` — sign in/register, upload CVs, view history.

Interactive API docs: `http://localhost:8000/docs`

### Dev Container (recommended)

Open in VS Code → "Reopen in Container". Dependencies install automatically, port 8000 is forwarded.

---

## API Reference

### `GET /health`

Health check.

**Response**
```json
{
  "status": "active",
  "engine": "EvalHire v1.0"
}
```

---

### `GET /`

Serves the landing page (`app/static/landing.html`).

---

### `GET /app`

Serves the browser app (`app/static/index.html`) — **Single CV**, **Batch**, **Compare**, and **History** tabs. Sign in or create an account to save evaluation history and access the Compare tab (authentication required).

---

### `POST /auth/register`

Create a new account.

**Request** — `application/json`

```json
{ "email": "you@example.com", "password": "yourpassword" }
```

**Response `201 Created`**
```json
{ "access_token": "<jwt>", "token_type": "bearer", "email": "you@example.com" }
```

---

### `POST /auth/login`

**Request** — `application/json`

```json
{ "email": "you@example.com", "password": "yourpassword" }
```

**Response `200 OK`** — same shape as `/auth/register`.

---

### `GET /auth/me`

Returns the current user's id, email, and created_at. Requires `Authorization: Bearer <token>`.

---

### `GET /history`

Returns the authenticated user's evaluations, newest first. Requires `Authorization: Bearer <token>`.

**Query parameters** (all optional)

| Param   | Default | Description                           |
|---------|---------|---------------------------------------|
| `skip`  | `0`     | Number of records to skip (offset)    |
| `limit` | `50`    | Maximum records to return (max 200)   |

```json
[
  {
    "id": 42,
    "created_at": "2026-05-14T18:30:00",
    "filename": "jane_cv.pdf",
    "jd_preview": "Senior AI Engineer…",
    "score": 87,
    "verdict": "Strong hire — ship it.",
    "critique": ["...", "...", "..."],
    "persona_used": "You are a Founding CTO…",
    "persona_id": 1,
    "dimensions": { "Agency": 9, "Technical Depth": 8, "Velocity": 7 },
    "percentile": 92,
    "contact_email": "jane@example.com",
    "contact_phone": "+44 7700 900123",
    "contact_linkedin": "https://linkedin.com/in/jane-doe"
  }
]
```

Evaluations are saved automatically to history whenever `/evaluate` or `/evaluate/batch` is called with a valid `Authorization: Bearer <token>` header. `/compare` does **not** write to history.

---

### `POST /evaluate`

Evaluate a candidate CV against a job description.

**Request** — `multipart/form-data`

| Field     | Type | Required | Description                                                        |
|-----------|------|----------|---------------------------------------------------------------------------------------------------------------------------------|
| `file`    | file | Yes      | Candidate CV — PDF only                                             |
| `jd`      | text | Yes      | Job description as plain text                                       |
| `persona`    | text | No       | Evaluator persona prompt (raw text). Ignored if `persona_id` is set. Defaults to Founding CTO if both omitted. |
| `persona_id` | int  | No       | ID of a persona from `GET /personas`. When set, `persona` is ignored and dimension names are resolved automatically. |

**Example (curl)**
```bash
curl -X POST http://localhost:8000/evaluate \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@candidate_cv.pdf" \
  -F "jd=We are looking for a Lead AI Engineer with strong FastAPI and LLM experience."
```

**With a custom persona**
```bash
curl -X POST http://localhost:8000/evaluate \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@candidate_cv.pdf" \
  -F "jd=Enterprise account executive role." \
  -F "persona=You are a VP of Sales at a B2B SaaS company. Evaluate for deal-closing instinct, resilience, and quota attainment."
```

**Response `200 OK`**
```json
{
  "status": "success",
  "data": {
    "filename": "candidate_cv.pdf",
    "analysis": {
      "score": 74,
      "critique": [
        "Strong ML fundamentals and shipped production models — clear technical depth.",
        "Limited evidence of leading initiatives without a manager; agency is implied but not proven.",
        "Job-hopped every 12 months — could signal velocity, could signal lack of follow-through."
      ],
      "verdict": "Promising technical profile, but needs a founder-style interview to validate ownership mindset.",
      "dimensions": { "Agency": 8, "Technical Depth": 9, "Velocity": 6 }
    },
    "contact": {
      "email": "jane@example.com",
      "phone": "+44 7700 900123",
      "linkedin": "https://linkedin.com/in/jane-doe"
    }
  },
  "percentile": 74
}
```

`dimensions` is populated when a persona with defined dimensions is used (either via `persona_id` or a system persona). `percentile` is the candidate's rank among all CVs evaluated under the same persona — only returned once 5+ records exist for that persona, otherwise `null`. Contact fields are `null` if not found in the CV. No LLM call is used for contact extraction — pure regex, zero added latency.

**Error responses**

| Status | Reason |
|--------|--------|
| `400`  | File is not a PDF |
| `401`  | `API_KEY` is set and the `X-API-Key` header is missing or wrong |
| `413`  | File exceeds 10 MB |
| `500`  | PDF text extraction failed or LLM returned a malformed response |
| `502`  | LLM API call failed |

---

### `POST /evaluate/batch`

Evaluate multiple CV PDFs against one job description. Returns all results ranked by score.

**Request** — `multipart/form-data`

| Field     | Type       | Required | Description                          |
|-----------|------------|----------|--------------------------------------|
| `files`   | file (1–N) | Yes      | One or more candidate CVs — PDF only |
| `jd`      | text       | Yes      | Job description as plain text        |
| `persona` | text       | No       | Evaluator persona prompt. Defaults to Founding CTO persona if omitted. |

**Example (curl)**
```bash
curl -X POST http://localhost:8000/evaluate/batch \
  -H "X-API-Key: your_api_key_here" \
  -F "files=@alice.pdf" \
  -F "files=@bob.pdf" \
  -F "jd=We are looking for a Lead AI Engineer."
```

**Response `200 OK`**
```json
{
  "status": "success",
  "jd_preview": "We are looking for a Lead AI Engineer.",
  "results": [
    {
      "filename": "alice.pdf",
      "score": 88,
      "verdict": "Strong hire — high agency and deep ML track record.",
      "error": null,
      "contact": {
        "email": "alice@example.com",
        "phone": null,
        "linkedin": "https://linkedin.com/in/alice-smith"
      }
    },
    {
      "filename": "bob.pdf",
      "score": 61,
      "verdict": "Borderline — good fundamentals but limited ownership signals.",
      "error": null,
      "contact": {
        "email": "bob@example.com",
        "phone": "+1 415 555 0199",
        "linkedin": null
      }
    }
  ]
}
```

Results are always sorted descending by score. Non-PDF files or files that fail extraction are included in results with `score: 0` and an `error` message rather than failing the whole request.

---

### `DELETE /auth/me`

Permanently deletes the authenticated user's account and all associated evaluation history. Requires `Authorization: Bearer <token>`.

**Response `204 No Content`** — no body.

---

### `POST /history/purge`

Deletes all evaluation history for the authenticated user. The account itself is preserved. Requires `Authorization: Bearer <token>`.

**Response `200 OK`**
```json
{ "deleted": 42 }
```

---

### `GET /personas`

Returns all public personas sorted by `use_count` descending (most popular first).

**Query parameters**

| Param   | Default | Description               |
|---------|---------|---------------------------|
| `skip`  | `0`     | Offset                    |
| `limit` | `50`    | Maximum records to return |

**Response `200 OK`**
```json
[
  {
    "id": 1,
    "name": "Founding CTO",
    "description": "Evaluates for high agency, technical depth, and execution velocity in early-stage startup contexts.",
    "prompt": "You are a Founding CTO of a high-growth AI startup…",
    "dimensions": ["Agency", "Technical Depth", "Velocity"],
    "is_public": true,
    "is_system": true,
    "author_id": null,
    "use_count": 412,
    "created_at": "2026-05-16T00:00:00"
  }
]
```

---

### `GET /personas/{persona_id}`

Returns a single public persona by ID, or `404` if not found.

---

### `POST /personas`

Create a custom persona. Requires `Authorization: Bearer <token>`.

**Request** — `application/json`

```json
{
  "name": "My Hiring Rubric",
  "description": "Optional description",
  "prompt": "You are a hiring manager at a fintech startup…",
  "dimensions": ["Risk Awareness", "Regulatory Knowledge"],
  "is_public": true
}
```

`name` and `prompt` are required. `dimensions` is an optional list of axis names the LLM will score 0–10.

**Response `201 Created`** — full `PersonaResponse` object.

---

### `POST /compare`

Evaluate and rank 2–10 candidate CVs against one job description in a single request. **Requires `Authorization: Bearer <token>`**.

**Request** — `multipart/form-data`

| Field        | Type        | Required | Description                                                       |
|--------------|-------------|----------|-------------------------------------------------------------------|
| `files`      | file (2–10) | Yes      | Candidate CVs — PDF only                                          |
| `jd`         | text        | Yes      | Job description as plain text                                     |
| `persona`    | text        | No       | Evaluator persona prompt. Ignored if `persona_id` is set.         |
| `persona_id` | int         | No       | Persona ID from `GET /personas`.                                  |

**Response `200 OK`**
```json
{
  "status": "success",
  "jd_preview": "Senior ML Engineer, London…",
  "persona_name": "Founding CTO",
  "results": [
    {
      "filename": "alice.pdf",
      "score": 91,
      "verdict": "Exceptional — clear founding-engineer DNA.",
      "dimensions": { "Agency": 10, "Technical Depth": 9, "Velocity": 9 },
      "contact": { "email": "alice@example.com", "phone": null, "linkedin": "https://linkedin.com/in/alice" },
      "error": null
    },
    {
      "filename": "bob.pdf",
      "score": 64,
      "verdict": "Solid IC, limited ownership signals.",
      "dimensions": { "Agency": 6, "Technical Depth": 8, "Velocity": 5 },
      "contact": { "email": "bob@example.com", "phone": null, "linkedin": null },
      "error": null
    }
  ]
}
```

Results are sorted descending by score. `/compare` does **not** write to evaluation history. Compare calls increment `use_count` on the persona (by the number of successfully evaluated CVs).

---

## Environment variables

| Variable                  | Required | Description                                                                                                               |
|---------------------------|----------|---------------------------------------------------------------------------------------------------------------------------|
| `MODEL_TOKEN`             | Yes      | API key for the LLM provider (GitHub Models, OpenAI, or Anthropic — see `MODEL_PROVIDER`)                                |
| `MODEL_PROVIDER`          | No       | LLM backend. One of `github` (default), `openai`, `anthropic`                                                            |
| `API_KEY`                 | No       | Key callers must send in `X-API-Key` header. Leave unset to disable auth (dev mode)                                      |
| `SECRET_KEY`              | No       | JWT signing secret. Auto-generated on startup if unset (tokens invalidate on restart)                                    |
| `DATABASE_URL`            | No       | SQLAlchemy database URL. Defaults to `sqlite:///./evalhire.db` for local dev. Set to Railway PostgreSQL URL in production.|
| `FREE_TIER_MONTHLY_LIMIT` | No       | Max `/evaluate` calls per user per calendar month. Defaults to `20`. Set to `0` to disable.                              |

> In CI, `MODEL_TOKEN` is injected from a GitHub Actions repository secret. Never commit `.env`.

---

## Running tests

```bash
export PYTHONPATH=$(pwd)
pytest
```

---

## Tech stack

| Layer        | Tech                                                       |
|--------------|------------------------------------------------------------|
| Landing page | Plain HTML/CSS served by FastAPI                           |
| App UI       | Plain HTML/CSS/JS served by FastAPI                        |
| API          | FastAPI 0.110 + uvicorn                                    |
| Auth         | JWT (python-jose) + bcrypt password hashing                |
| Database     | SQLAlchemy 2.0 — SQLite locally, PostgreSQL on Railway     |
| PDF parsing  | pdfplumber 0.11                                            |
| LLM          | Llama 3.3 70B (GitHub Models, default), GPT-4o (OpenAI), Claude 3.5 Sonnet (Anthropic) |
| LLM client   | OpenAI Python SDK 1.12 (OpenAI-spec endpoint for all three providers)                   |
| CI           | GitHub Actions — runs pytest on every push/PR              |
| Dev env      | VS Code Dev Container (Python 3.10)                        |

---

## Project structure

```
app/
├── main.py              # FastAPI routes — /, /app, /health, /evaluate, /evaluate/batch, /compare, /auth/*, /history, /personas
├── auth.py              # JWT + X-API-Key auth, password hashing (bcrypt)
├── database.py          # SQLAlchemy engine + session factory
├── db_models.py         # ORM models: User, EvaluationRecord, Persona
├── models.py            # Pydantic request/response schemas
├── routers/
│   ├── auth_routes.py   # POST /auth/register, /auth/login, GET /auth/me, DELETE /auth/me
│   ├── history_routes.py# GET /history (paginated), POST /history/purge
│   └── persona_routes.py# GET /personas, GET /personas/{id}, POST /personas
├── engine/
│   ├── logic.py         # LLM evaluation (multi-provider: GitHub Models / OpenAI / Anthropic)
│   └── personas_seed.py # 15 curated system personas — seeded on startup
├── utils/
│   └── extractor.py     # PDF → text + contact info extraction
└── static/
    ├── landing.html     # Marketing landing page
    └── index.html       # Browser app (Single CV + Batch + Compare + History tabs)
tests/
├── test_main.py
└── test_personas.py     # 15 Phase 1 tests covering /personas and /compare
.github/workflows/
└── ci.yml
```