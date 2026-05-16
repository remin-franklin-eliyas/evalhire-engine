import json
import io
import os
import uuid
import threading

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List

from app.utils.extractor import extract_text_from_pdf, extract_contact_info
from app.engine.logic import evaluate_cv, DEFAULT_PERSONA
from app.models import (
    EvaluationResult, EvaluationData, EvaluationResponse,
    BatchResultItem, BatchResponse, JobCreatedResponse, JobStatusResponse,
)
from app.auth import verify_api_key, get_optional_user
from app.database import engine, get_db
from app.routers import auth_routes, history_routes

MAX_UPLOAD_BYTES = 10 * 1024 * 1024          # 10 MB per file
MAX_AGGREGATE_BATCH_BYTES = 50 * 1024 * 1024  # 50 MB total across all files in a batch
FREE_TIER_MONTHLY_LIMIT = 20

# ── In-memory job store for async batch processing ────────────────────────────
_jobs: dict = {}
_jobs_lock = threading.Lock()

# ── Create DB tables on startup ───────────────────────────────────────────────
from app.db_models import User, EvaluationRecord  # noqa: F401 — registers models with Base
from app.database import Base
from datetime import datetime, timezone
Base.metadata.create_all(bind=engine)

# ── Inline migration: add columns that may be missing from older DBs ──────────
with engine.connect() as _conn:
    from sqlalchemy import text as _text
    try:
        _conn.execute(_text("ALTER TABLE users ADD COLUMN tier TEXT NOT NULL DEFAULT 'free'"))
        _conn.commit()
    except Exception:
        pass  # column already exists


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


@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(os.path.join(_static_dir, "landing.html"))


@app.get("/app", response_class=FileResponse)
def app_ui():
    return FileResponse(os.path.join(_static_dir, "index.html"))


@app.get("/health")
def health_check():
    return {"status": "active", "engine": "EvalHire v1.0"}


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_candidate(
    file: UploadFile = File(...),
    jd: str = Form(...),
    persona: str = Form(default=""),
    _: None = Depends(verify_api_key),
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")
    extracted_text = extract_text_from_pdf(io.BytesIO(content))

    if "Error" in extracted_text:
        raise HTTPException(status_code=500, detail="Failed to extract text from CV.")

    _check_free_tier(current_user, db)

    active_persona = persona.strip() or DEFAULT_PERSONA
    try:
        raw = evaluate_cv(extracted_text, jd, persona=active_persona)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"LLM unavailable: {str(e)}")

    try:
        analysis = EvaluationResult(**raw)
    except Exception:
        raise HTTPException(status_code=500, detail="LLM returned a malformed response.")

    contact = extract_contact_info(extracted_text)

    if current_user:
        record = EvaluationRecord(
            user_id=current_user.id,
            filename=file.filename,
            jd_preview=jd[:300],
            score=analysis.score,
            verdict=analysis.verdict,
            critique_json=json.dumps(analysis.critique),
            persona_used=active_persona,
            contact_email=contact.email,
            contact_phone=contact.phone,
            contact_linkedin=contact.linkedin,
        )
        db.add(record)
        db.commit()

    return EvaluationResponse(
        status="success",
        data=EvaluationData(filename=file.filename, analysis=analysis, contact=contact),
    )


def _process_batch_job(
    job_id: str,
    files_data: list,
    jd: str,
    persona: str,
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
                extracted_text = extract_text_from_pdf(io.BytesIO(content))
                if "Error" in extracted_text:
                    results.append({"filename": filename, "score": 0, "verdict": "Skipped",
                                     "error": "Failed to extract text from PDF.", "contact": None})
                else:
                    try:
                        raw = evaluate_cv(extracted_text, jd, persona=persona)
                        analysis = EvaluationResult(**raw)
                        contact = extract_contact_info(extracted_text)
                        results.append({
                            "filename": filename,
                            "score": analysis.score,
                            "verdict": analysis.verdict,
                            "error": None,
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
                                contact_email=contact.email if contact else None,
                                contact_phone=contact.phone if contact else None,
                                contact_linkedin=contact.linkedin if contact else None,
                            ))
                    except Exception as exc:
                        results.append({"filename": filename, "score": 0,
                                         "verdict": "Evaluation failed", "error": str(exc),
                                         "contact": None})

            with _jobs_lock:
                _jobs[job_id]["processed"] += 1

        results.sort(key=lambda r: r["score"], reverse=True)
        if user_id is not None:
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

    active_persona = persona.strip() or DEFAULT_PERSONA
    background_tasks.add_task(
        _process_batch_job, job_id, files_data, jd, active_persona,
        current_user.id if current_user else None,
    )
    return JobCreatedResponse(job_id=job_id, status="pending", total=len(files_data))


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatusResponse(job_id=job_id, **job)