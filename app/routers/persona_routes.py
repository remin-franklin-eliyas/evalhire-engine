import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.db_models import Persona, User
from app.models import PersonaCreate, PersonaResponse
from app.auth import get_current_user

router = APIRouter(prefix="/personas", tags=["personas"])


def _to_response(p: Persona) -> PersonaResponse:
    return PersonaResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        prompt=p.prompt,
        dimensions=p.dimension_names(),
        is_public=p.is_public,
        is_system=p.is_system,
        author_id=p.author_id,
        use_count=p.use_count,
        created_at=p.created_at.isoformat(),
    )


@router.get("", response_model=List[PersonaResponse])
def list_personas(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Browse public personas sorted by popularity."""
    limit = min(limit, 100)
    personas = (
        db.query(Persona)
        .filter(Persona.is_public == True)  # noqa: E712
        .order_by(Persona.use_count.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_response(p) for p in personas]


@router.get("/{persona_id}", response_model=PersonaResponse)
def get_persona(persona_id: int, db: Session = Depends(get_db)):
    """Get a single public persona by ID."""
    p = db.query(Persona).filter(Persona.id == persona_id).first()
    if p is None or not p.is_public:
        raise HTTPException(status_code=404, detail="Persona not found.")
    return _to_response(p)


@router.post("", response_model=PersonaResponse, status_code=201)
def create_persona(
    body: PersonaCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a custom persona. Requires authentication."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Persona name is required.")
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Persona prompt is required.")
    p = Persona(
        name=body.name.strip(),
        description=body.description,
        prompt=body.prompt.strip(),
        dimensions=json.dumps(body.dimensions),
        author_id=current_user.id,
        is_public=body.is_public,
        is_system=False,
        use_count=0,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_response(p)
