from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.utils.extractor import extract_text_from_pdf, extract_contact_info
from app.engine.logic import evaluate_cv, DEFAULT_PERSONA
from app.models import EvaluationResult, EvaluationData, EvaluationResponse, BatchResultItem, BatchResponse
from app.auth import verify_api_key
from typing import List
import io
import os

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

app = FastAPI(title="EvalHire Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/", response_class=FileResponse)
def index():
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
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")
    extracted_text = extract_text_from_pdf(io.BytesIO(content))

    if "Error" in extracted_text:
        raise HTTPException(status_code=500, detail="Failed to extract text from CV.")

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
    return EvaluationResponse(
        status="success",
        data=EvaluationData(filename=file.filename, analysis=analysis, contact=contact),
    )


@app.post("/evaluate/batch", response_model=BatchResponse)
async def evaluate_batch(
    files: List[UploadFile] = File(...),
    jd: str = Form(...),
    persona: str = Form(default=""),
    _: None = Depends(verify_api_key),
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    active_persona = persona.strip() or DEFAULT_PERSONA
    results = []
    for upload in files:
        if upload.content_type != "application/pdf":
            results.append(BatchResultItem(
                filename=upload.filename,
                score=0,
                verdict="Skipped",
                error="Not a PDF file.",
            ))
            continue

        content = await upload.read()
        if len(content) > MAX_UPLOAD_BYTES:
            results.append(BatchResultItem(
                filename=upload.filename,
                score=0,
                verdict="Skipped",
                error="File too large. Maximum size is 10 MB.",
            ))
            continue

        extracted_text = extract_text_from_pdf(io.BytesIO(content))
        if "Error" in extracted_text:
            results.append(BatchResultItem(
                filename=upload.filename,
                score=0,
                verdict="Skipped",
                error="Failed to extract text from PDF.",
            ))
            continue

        try:
            raw = evaluate_cv(extracted_text, jd, persona=active_persona)
            analysis = EvaluationResult(**raw)
            contact = extract_contact_info(extracted_text)
            results.append(BatchResultItem(
                filename=upload.filename,
                score=analysis.score,
                verdict=analysis.verdict,
                contact=contact,
            ))
        except Exception as e:
            results.append(BatchResultItem(
                filename=upload.filename,
                score=0,
                verdict="Evaluation failed",
                error=str(e),
            ))

    results.sort(key=lambda r: r.score, reverse=True)

    return BatchResponse(
        status="success",
        jd_preview=jd[:200],
        results=results,
    )