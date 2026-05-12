from fastapi import FastAPI, UploadFile, File, HTTPException
from app.utils.extractor import extract_text_from_pdf
import io

app = FastAPI(title="EvalHire Engine")

@app.get("/")
def health_check():
    return {"status": "active", "engine": "EvalHire v1.0"}

@app.post("/extract")
async def upload_cv(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    content = await file.read()
    extracted_text = extract_text_from_pdf(io.BytesIO(content))
    
    return {"filename": file.filename, "text_preview": extracted_text[:500]}