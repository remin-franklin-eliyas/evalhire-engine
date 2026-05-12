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
    jd: str = Form(...)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    content = await file.read()
    extracted_text = extract_text_from_pdf(io.BytesIO(content))
    
    if "Error" in extracted_text:
        raise HTTPException(status_code=500, detail="Failed to extract text from CV.")

    # This now returns a dictionary
    analysis = evaluate_cv(extracted_text, jd)
    
    return {
        "status": "success",
        "data": {
            "filename": file.filename,
            "analysis": analysis
        }
    }