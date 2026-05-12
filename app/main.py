from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from app.utils.extractor import extract_text_from_pdf
from app.engine.logic import evaluate_cv
import io

app = FastAPI(title="EvalHire Engine")

@app.get("/")
def health_check():
    return {"status": "active", "engine": "EvalHire v1.0"}

@app.post("/evaluate")
async def evaluate_candidate(
    file: UploadFile = File(...), 
    jd: str = Form(...) # We accept the JD as a form field
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    # 1. Extract
    content = await file.read()
    extracted_text = extract_text_from_pdf(io.BytesIO(content))
    
    if "Error" in extracted_text:
        raise HTTPException(status_code=500, detail=extracted_text)

    # 2. Evaluate via Llama 3
    evaluation = evaluate_cv(extracted_text, jd)
    
    return {
        "filename": file.filename,
        "evaluation": evaluation
    }