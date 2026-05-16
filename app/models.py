from pydantic import BaseModel, Field
from typing import List, Dict


class ContactInfo(BaseModel):
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None


class EvaluationResult(BaseModel):
    score: int = Field(..., ge=0, le=100)
    critique: List[str]
    verdict: str
    dimensions: Dict[str, int] = {}


class EvaluationData(BaseModel):
    filename: str
    analysis: EvaluationResult
    contact: ContactInfo | None = None


class EvaluationResponse(BaseModel):
    status: str
    data: EvaluationData
    percentile: int | None = None


class BatchResultItem(BaseModel):
    filename: str
    score: int = Field(..., ge=0, le=100)
    verdict: str
    error: str | None = None
    contact: ContactInfo | None = None


class BatchResponse(BaseModel):
    status: str
    jd_preview: str
    results: List[BatchResultItem]


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str  # "pending"
    total: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "pending" | "processing" | "complete" | "error"
    total: int
    processed: int
    jd_preview: str | None = None
    results: List[BatchResultItem] | None = None
    error: str | None = None
    created_at: str


class PersonaCreate(BaseModel):
    name: str
    description: str | None = None
    prompt: str
    dimensions: List[str] = []
    is_public: bool = True


class PersonaResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    prompt: str
    dimensions: List[str] = []
    is_public: bool
    is_system: bool
    author_id: int | None = None
    use_count: int
    created_at: str

    class Config:
        from_attributes = True


class CompareResultItem(BaseModel):
    filename: str
    score: int = Field(..., ge=0, le=100)
    verdict: str
    dimensions: Dict[str, int] = {}
    contact: ContactInfo | None = None
    error: str | None = None


class CompareResponse(BaseModel):
    status: str
    jd_preview: str
    persona_name: str | None = None
    results: List[CompareResultItem]
