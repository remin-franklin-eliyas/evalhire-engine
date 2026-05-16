import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Dict

from app.database import get_db
from app.db_models import EvaluationRecord, User
from app.auth import get_current_user

router = APIRouter(prefix="/history", tags=["history"])


class HistoryItem(BaseModel):
    id: int
    created_at: str
    filename: str
    jd_preview: Optional[str]
    score: int
    verdict: Optional[str]
    critique: list
    persona_used: Optional[str]
    persona_id: Optional[int] = None
    dimensions: Dict[str, int] = {}
    percentile: Optional[int] = None
    contact_email: Optional[str]
    contact_phone: Optional[str]
    contact_linkedin: Optional[str]


@router.get("", response_model=list[HistoryItem])
def get_history(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = min(limit, 200)  # hard cap — no single request returns more than 200
    records = (
        db.query(EvaluationRecord)
        .filter(EvaluationRecord.user_id == current_user.id)
        .order_by(EvaluationRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        HistoryItem(
            id=r.id,
            created_at=r.created_at.isoformat(),
            filename=r.filename,
            jd_preview=r.jd_preview,
            score=r.score or 0,
            verdict=r.verdict,
            critique=r.critique(),
            persona_used=r.persona_used,
            persona_id=r.persona_id,
            dimensions=r.dimension_scores(),
            percentile=r.percentile,
            contact_email=r.contact_email,
            contact_phone=r.contact_phone,
            contact_linkedin=r.contact_linkedin,
        )
        for r in records
    ]


@router.post("/purge", status_code=204)
def purge_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all evaluation history for the current user (GDPR right to erasure)."""
    db.query(EvaluationRecord).filter(
        EvaluationRecord.user_id == current_user.id
    ).delete(synchronize_session=False)
    db.commit()
