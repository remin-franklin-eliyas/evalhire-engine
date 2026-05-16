import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    tier            = Column(String, nullable=False, default="free", server_default="free")

    evaluations = relationship("EvaluationRecord", back_populates="user",
                               cascade="all, delete-orphan")
    personas    = relationship("Persona", back_populates="author",
                               cascade="all, delete-orphan",
                               foreign_keys="Persona.author_id")


class Persona(Base):
    __tablename__ = "personas"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    description = Column(Text)
    prompt      = Column(Text, nullable=False)
    dimensions  = Column(Text)          # JSON list of dimension name strings
    author_id   = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = system persona
    is_public   = Column(Boolean, default=True, nullable=False)
    is_system   = Column(Boolean, default=False, nullable=False)
    use_count   = Column(Integer, default=0, nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    author = relationship("User", back_populates="personas", foreign_keys=[author_id])

    def dimension_names(self) -> list:
        try:
            return json.loads(self.dimensions or "[]")
        except Exception:
            return []


class EvaluationRecord(Base):
    __tablename__ = "evaluations"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    filename         = Column(String, nullable=False)
    jd_preview       = Column(Text)
    score            = Column(Integer)
    verdict          = Column(Text)
    critique_json    = Column(Text)          # JSON list[str]
    persona_used     = Column(Text)
    persona_id       = Column(Integer, ForeignKey("personas.id"), nullable=True)
    dimensions_json  = Column(Text)          # JSON dict {dimension: score}
    percentile       = Column(Integer, nullable=True)
    contact_email    = Column(String)
    contact_phone    = Column(String)
    contact_linkedin = Column(String)

    user    = relationship("User", back_populates="evaluations")
    persona = relationship("Persona")

    def critique(self) -> list:
        try:
            return json.loads(self.critique_json or "[]")
        except Exception:
            return []

    def dimension_scores(self) -> dict:
        try:
            return json.loads(self.dimensions_json or "{}")
        except Exception:
            return {}
