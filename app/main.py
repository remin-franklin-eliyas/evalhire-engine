from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from app.utils.extractor import extract_text_from_pdf
from app.engine.logic import evaluate_cv
from app.models import EvaluationResult, EvaluationData, EvaluationResponse
from app.auth import verify_api_key
import io

app = FastAPI(title="EvalHire Engine")


@app.get("/")
def health_check():
    return {"status": "active", "engine": "EvalHire v1.0"}


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_candidate(
    file: UploadFile = File(...),
    jd: str = Form(...),
    _: None = Depends(verify_api_key),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    extracted_text = extract_text_from_pdf(io.BytesIO(content))

    if "Error" in extracted_text:
        raise HTTPException(status_code=500, detail="Failed to extract text from CV.")

    raw = evaluate_cv(extracted_text, jd)

    try:
        analysis = EvaluationResult(**raw)
    except Exception:
        raise HTTPException(status_code=500, detail="LLM returned a malformed response.")

    return EvaluationResponse(
        status="success",
        data=EvaluationData(filename=file.filename, analysis=analysis),
    )