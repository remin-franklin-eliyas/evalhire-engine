import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

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
    contact_email: Optional[str]
    contact_phone: Optional[str]
    contact_linkedin: Optional[str]


@router.get("", response_model=list[HistoryItem])
def get_history(current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    records = (
        db.query(EvaluationRecord)
        .filter(EvaluationRecord.user_id == current_user.id)
        .order_by(EvaluationRecord.created_at.desc())
        .limit(200)
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
            contact_email=r.contact_email,
            contact_phone=r.contact_phone,
            contact_linkedin=r.contact_linkedin,
        )
        for r in records
    ]
