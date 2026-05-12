# EvalHire Engine

An AI-powered CV screening API built for startup hiring. Upload a PDF CV and a job description — get back a structured score, critique, and hire/no-hire verdict in seconds, evaluated through the lens of a Founding CTO.

---

## How it works

1. You `POST` a candidate's PDF CV + a job description to `/evaluate`
2. The engine extracts the CV text from the PDF
3. It sends both to **Llama 3 70B** (via GitHub Models) with a CTO-persona prompt
4. Returns a structured JSON evaluation scored on **High Agency**, **Technical Depth**, and **Velocity**

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

Interactive docs: `http://localhost:8000/docs`

### Dev Container (recommended)

Open in VS Code → "Reopen in Container". Dependencies install automatically, port 8000 is forwarded.

---

## API Reference

### `GET /`

Health check.

**Response**
```json
{
  "status": "active",
  "engine": "EvalHire v1.0"
}
```

---

### `POST /evaluate`

Evaluate a candidate CV against a job description.

**Request** — `multipart/form-data`

| Field  | Type | Description                  |
|--------|------|------------------------------|
| `file` | file | Candidate CV — PDF only      |
| `jd`   | text | Job description as plain text |

**Example (curl)**
```bash
curl -X POST http://localhost:8000/evaluate \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@candidate_cv.pdf" \
  -F "jd=We are looking for a Lead AI Engineer with strong FastAPI and LLM experience."
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
      "verdict": "Promising technical profile, but needs a founder-style interview to validate ownership mindset."
    }
  }
}
```

**Error responses**

| Status | Reason |
|--------|--------|
| `400`  | File is not a PDF |
| `401`  | `API_KEY` is set and the `X-API-Key` header is missing or wrong |
| `500`  | PDF text extraction failed or LLM call failed |

---

## Environment variables

| Variable      | Required | Description                                        |
|---------------|----------|----------------------------------------------------|
| `MODEL_TOKEN` | Yes      | API key for GitHub Models (or any OpenAI-spec provider) || `API_KEY`     | No       | Key callers must send in `X-API-Key` header. Leave unset to disable auth (dev mode) |
> In CI, `MODEL_TOKEN` is injected from a GitHub Actions repository secret. Never commit `.env`.

---

## Running tests

```bash
export PYTHONPATH=$(pwd)
pytest
```

---

## Tech stack

| Layer       | Tech                              |
|-------------|-----------------------------------|
| API         | FastAPI 0.110 + uvicorn           |
| PDF parsing | pdfplumber 0.11                   |
| LLM         | Llama 3 70B via GitHub Models     |
| LLM client  | OpenAI Python SDK 1.12 (OpenAI-spec) |
| CI          | GitHub Actions — runs pytest on every push/PR |
| Dev env     | VS Code Dev Container (Python 3.10) |

---

## Project structure

```
app/
├── main.py           # FastAPI routes
├── engine/
│   └── logic.py      # LLM evaluation logic
└── utils/
    └── extractor.py  # PDF → text
tests/
└── test_main.py
.github/workflows/
└── ci.yml
```