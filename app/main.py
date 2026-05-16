import json
import io
import os
import uuid
import threading
import asyncio

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List

from app.utils.extractor import extract_text_from_pdf, extract_contact_info
from app.engine.logic import evaluate_cv, DEFAULT_PERSONA
from app.engine.personas_seed import seed_system_personas
from app.models import (
    EvaluationResult, EvaluationData, EvaluationResponse,
    BatchResultItem, BatchResponse, JobCreatedResponse, JobStatusResponse,
    PersonaCreate, PersonaResponse, CompareResultItem, CompareResponse,
)
from app.auth import verify_api_key, get_optional_user, get_current_user
from app.database import engine, get_db, SessionLocal
from app.routers import auth_routes, history_routes, persona_routes

MAX_UPLOAD_BYTES = 10 * 1024 * 1024          # 10 MB per file
MAX_AGGREGATE_BATCH_BYTES = 50 * 1024 * 1024  # 50 MB total across all files in a batch
FREE_TIER_MONTHLY_LIMIT = int(os.getenv("FREE_TIER_MONTHLY_LIMIT", "20"))

# ── In-memory job store for async batch processing ────────────────────────────
_jobs: dict = {}
_jobs_lock = threading.Lock()

# ── Create DB tables on startup ───────────────────────────────────────────────
from app.db_models import User, EvaluationRecord, Persona  # noqa: F401 — registers models with Base
from app.database import Base
from datetime import datetime, timezone
Base.metadata.create_all(bind=engine)

# ── Inline migrations: add columns that may be missing from older DBs ─────────
_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN tier TEXT NOT NULL DEFAULT 'free'",
    "ALTER TABLE evaluations ADD COLUMN persona_id INTEGER REFERENCES personas(id)",
    "ALTER TABLE evaluations ADD COLUMN dimensions_json TEXT",
    "ALTER TABLE evaluations ADD COLUMN percentile INTEGER",
]
with engine.connect() as _conn:
    from sqlalchemy import text as _text
    for _sql in _MIGRATIONS:
        try:
            _conn.execute(_text(_sql))
            _conn.commit()
        except Exception:
            pass  # column/table already exists

# ── Seed curated system personas ───────────────────────────────────────────────
with SessionLocal() as _seed_db:
    seed_system_personas(_seed_db)


def _check_free_tier(user, db: Session, slots_needed: int = 1) -> None:
    """Raises HTTP 429 if a free-tier user has hit their monthly evaluation cap."""
    if user is None or user.tier != "free":
        return
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    used = (
        db.query(EvaluationRecord)
        .filter(
            EvaluationRecord.user_id == user.id,
            EvaluationRecord.created_at >= month_start,
        )
        .count()
    )
    remaining = FREE_TIER_MONTHLY_LIMIT - used
    if remaining < slots_needed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Free tier limit reached — {FREE_TIER_MONTHLY_LIMIT} evaluations/month. "
                f"You have {max(0, remaining)} remaining this month. "
                "Upgrade to Pro for unlimited screening."
            ),
        )

app = FastAPI(title="EvalHire Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.include_router(auth_routes.router)
app.include_router(history_routes.router)
app.include_router(persona_routes.router)


@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(os.path.join(_static_dir, "landing.html"))


@app.get("/app", response_class=FileResponse)
def app_ui():
    return FileResponse(os.path.join(_static_dir, "index.html"))


@app.get("/health")
def health_check():
    return {"status": "active", "engine": "EvalHire v1.0"}


def _resolve_persona(persona_id: int | None, persona_text: str, db: Session):
    """Return (prompt, dimension_names, persona_obj | None)."""
    if persona_id is not None:
        p = db.query(Persona).filter(Persona.id == persona_id).first()
        if p is None or not p.is_public:
            raise HTTPException(status_code=404, detail="Persona not found.")
        return p.prompt, p.dimension_names(), p
    return persona_text.strip() or DEFAULT_PERSONA, [], None


def _compute_percentile(persona_id: int, score: int, db: Session) -> int | None:
    """Percentile rank of this score among all evaluations with the same persona.
    Returns None if fewer than 5 records exist (not enough data).
    """
    total = (
        db.query(EvaluationRecord)
        .filter(EvaluationRecord.persona_id == persona_id)
        .count()
    )
    if total < 5:
        return None
    lower = (
        db.query(EvaluationRecord)
        .filter(
            EvaluationRecord.persona_id == persona_id,
            EvaluationRecord.score < score,
        )
        .count()
    )
    return round((lower / total) * 100)


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_candidate(
    file: UploadFile = File(...),
    jd: str = Form(...),
    persona: str = Form(default=""),
    persona_id: int | None = Form(default=None),
    _: None = Depends(verify_api_key),
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")
    try:
        extracted_text = extract_text_from_pdf(io.BytesIO(content))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to extract text from CV: {exc}")

    _check_free_tier(current_user, db)

    active_prompt, dimension_names, persona_obj = _resolve_persona(persona_id, persona, db)
    try:
        raw = evaluate_cv(extracted_text, jd, persona=active_prompt, dimension_names=dimension_names or None)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"LLM unavailable: {str(e)}")

    try:
        analysis = EvaluationResult(**raw)
    except Exception:
        raise HTTPException(status_code=500, detail="LLM returned a malformed response.")

    contact = extract_contact_info(extracted_text)
    percentile: int | None = None

    if current_user:
        record = EvaluationRecord(
            user_id=current_user.id,
            filename=file.filename,
            jd_preview=jd[:300],
            score=analysis.score,
            verdict=analysis.verdict,
            critique_json=json.dumps(analysis.critique),
            persona_used=active_prompt,
            persona_id=persona_obj.id if persona_obj else None,
            dimensions_json=json.dumps(analysis.dimensions) if analysis.dimensions else None,
        )
        record.contact_email = contact.email
        record.contact_phone = contact.phone
        record.contact_linkedin = contact.linkedin
        db.add(record)
        db.commit()
        db.refresh(record)

        if persona_obj:
            percentile = _compute_percentile(persona_obj.id, analysis.score, db)
            record.percentile = percentile
            # Increment use_count
            persona_obj.use_count += 1
            db.commit()

    return EvaluationResponse(
        status="success",
        data=EvaluationData(filename=file.filename, analysis=analysis, contact=contact),
        percentile=percentile,
    )


# ── Concurrent compare helpers ─────────────────────────────────────────────
_COMPARE_SEMAPHORE = asyncio.Semaphore(5)  # max 5 concurrent LLM calls


async def _evaluate_compare_file(
    filename: str,
    content: bytes,
    content_type: str,
    jd: str,
    active_prompt: str,
    dimension_names: list,
) -> CompareResultItem:
    """Evaluate one CV for /compare, running blocking work in the thread pool."""
    if len(content) > MAX_UPLOAD_BYTES:
        return CompareResultItem(
            filename=filename, score=0, verdict="Skipped",
            error="File too large. Maximum size is 10 MB.",
        )
    if content_type != "application/pdf":
        return CompareResultItem(
            filename=filename, score=0, verdict="Skipped",
            error="Not a PDF file.",
        )
    async with _COMPARE_SEMAPHORE:
        loop = asyncio.get_running_loop()
        try:
            extracted_text = await loop.run_in_executor(
                None, extract_text_from_pdf, io.BytesIO(content)
            )
        except RuntimeError:
            return CompareResultItem(
                filename=filename, score=0, verdict="Skipped",
                error="Failed to extract text from PDF.",
            )
        try:
            raw = await loop.run_in_executor(
                None,
                lambda: evaluate_cv(
                    extracted_text, jd,
                    persona=active_prompt,
                    dimension_names=dimension_names or None,
                ),
            )
            analysis = EvaluationResult(**raw)
            contact = await loop.run_in_executor(None, extract_contact_info, extracted_text)
            return CompareResultItem(
                filename=filename,
                score=analysis.score,
                verdict=analysis.verdict,
                dimensions=analysis.dimensions,
                contact=contact,
            )
        except Exception as exc:
            return CompareResultItem(
                filename=filename, score=0,
                verdict="Evaluation failed", error=str(exc),
            )


@app.post("/compare", response_model=CompareResponse)
async def compare_candidates(
    files: List[UploadFile] = File(...),
    jd: str = Form(...),
    persona: str = Form(default=""),
    persona_id: int | None = Form(default=None),
    _: None = Depends(verify_api_key),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate 2–10 CVs side-by-side and return a ranked comparison. Requires auth."""
    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="At least 2 files are required for comparison.")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per comparison.")
    if not jd.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")

    active_prompt, dimension_names, persona_obj = _resolve_persona(persona_id, persona, db)

    # Read all file contents eagerly — UploadFile objects are not safe to pass into thread executors
    _file_payloads: list[tuple[str, bytes, str]] = []
    for upload in files:
        _file_payloads.append((upload.filename, await upload.read(), upload.content_type))

    results = list(await asyncio.gather(*[
        _evaluate_compare_file(fn, c, ct, jd, active_prompt, dimension_names)
        for fn, c, ct in _file_payloads
    ]))
    results.sort(key=lambda r: r.score, reverse=True)

    if persona_obj:
        persona_obj.use_count += len([r for r in results if not r.error])
        db.commit()

    return CompareResponse(
        status="success",
        jd_preview=jd[:200],
        persona_name=persona_obj.name if persona_obj else None,
        results=results,
    )


def _process_batch_job(
    job_id: str,
    files_data: list,
    jd: str,
    persona: str,
    dimension_names: list,
    persona_id: int | None,
    user_id: int | None,
) -> None:
    """Background task: evaluate each CV and write results to the job store."""
    from app.database import SessionLocal

    with _jobs_lock:
        _jobs[job_id]["status"] = "processing"

    results = []
    db = SessionLocal()
    try:
        for file_data in files_data:
            filename = file_data["filename"]
            content = file_data["content"]

            if file_data.get("oversized"):
                results.append({"filename": filename, "score": 0, "verdict": "Skipped",
                                 "error": "File too large. Maximum size is 10 MB.", "contact": None})
            elif file_data["content_type"] != "application/pdf":
                results.append({"filename": filename, "score": 0, "verdict": "Skipped",
                                 "error": "Not a PDF file.", "contact": None})
            else:
                try:
                    extracted_text = extract_text_from_pdf(io.BytesIO(content))
                except RuntimeError:
                    results.append({"filename": filename, "score": 0, "verdict": "Skipped",
                                     "error": "Failed to extract text from PDF.", "contact": None,
                                     "dimensions": {}})
                else:
                    try:
                        raw = evaluate_cv(extracted_text, jd, persona=persona,
                                          dimension_names=dimension_names or None)
                        analysis = EvaluationResult(**raw)
                        contact = extract_contact_info(extracted_text)
                        results.append({
                            "filename": filename,
                            "score": analysis.score,
                            "verdict": analysis.verdict,
                            "error": None,
                            "dimensions": analysis.dimensions,
                            "contact": contact.model_dump() if contact else None,
                        })
                        if user_id is not None:
                            db.add(EvaluationRecord(
                                user_id=user_id,
                                filename=filename,
                                jd_preview=jd[:300],
                                score=analysis.score,
                                verdict=analysis.verdict,
                                critique_json=json.dumps(analysis.critique),
                                persona_used=persona,
                                persona_id=persona_id,
                                dimensions_json=json.dumps(analysis.dimensions) if analysis.dimensions else None,
                                contact_email=contact.email if contact else None,
                                contact_phone=contact.phone if contact else None,
                                contact_linkedin=contact.linkedin if contact else None,
                            ))
                    except Exception as exc:
                        results.append({"filename": filename, "score": 0,
                                         "verdict": "Evaluation failed", "error": str(exc),
                                         "contact": None, "dimensions": {}})

            with _jobs_lock:
                _jobs[job_id]["processed"] += 1

        results.sort(key=lambda r: r["score"], reverse=True)
        if persona_id is not None:
            _p = db.query(Persona).filter(Persona.id == persona_id).first()
            if _p:
                _p.use_count += sum(1 for r in results if not r.get("error"))
        if user_id is not None or persona_id is not None:
            db.commit()

        with _jobs_lock:
            _jobs[job_id]["status"] = "complete"
            _jobs[job_id]["results"] = results

    except Exception as exc:
        db.rollback()
        with _jobs_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(exc)
    finally:
        db.close()


@app.post("/evaluate/batch", response_model=JobCreatedResponse, status_code=202)
async def evaluate_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    jd: str = Form(...),
    persona: str = Form(default=""),
    persona_id: int | None = Form(default=None),
    _: None = Depends(verify_api_key),
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")
    if not jd.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")

    # Read all file bytes eagerly — UploadFile objects are not safe to use after response is sent
    files_data = []
    total_bytes = 0
    for upload in files:
        content = await upload.read()
        total_bytes += len(content)
        if total_bytes > MAX_AGGREGATE_BATCH_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Total upload size exceeds {MAX_AGGREGATE_BATCH_BYTES // (1024 * 1024)} MB.",
            )
        files_data.append({
            "filename": upload.filename,
            "content": content,
            "content_type": upload.content_type,
            "oversized": len(content) > MAX_UPLOAD_BYTES,
        })

    # Free tier check runs synchronously before the job is accepted
    pdf_count = sum(
        1 for f in files_data
        if f["content_type"] == "application/pdf" and not f["oversized"]
    )
    _check_free_tier(current_user, db, slots_needed=pdf_count)

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total": len(files_data),
            "processed": 0,
            "jd_preview": jd[:200],
            "results": None,
            "error": None,
        }

    active_prompt, dimension_names, persona_obj = _resolve_persona(persona_id, persona, db)
    resolved_persona_id = persona_obj.id if persona_obj else None
    background_tasks.add_task(
        _process_batch_job, job_id, files_data, jd, active_prompt, dimension_names,
        resolved_persona_id, current_user.id if current_user else None,
    )
    return JobCreatedResponse(job_id=job_id, status="pending", total=len(files_data))


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatusResponse(job_id=job_id, **job)