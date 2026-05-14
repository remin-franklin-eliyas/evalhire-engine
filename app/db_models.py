import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    evaluations = relationship("EvaluationRecord", back_populates="user",
                               cascade="all, delete-orphan")


class EvaluationRecord(Base):
    __tablename__ = "evaluations"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    filename       = Column(String, nullable=False)
    jd_preview     = Column(Text)
    score          = Column(Integer)
    verdict        = Column(Text)
    critique_json  = Column(Text)   # JSON-encoded list[str]
    persona_used   = Column(Text)
    contact_email  = Column(String)
    contact_phone  = Column(String)
    contact_linkedin = Column(String)

    user = relationship("User", back_populates="evaluations")

    def critique(self) -> list:
        try:
            return json.loads(self.critique_json or "[]")
        except Exception:
            return []
