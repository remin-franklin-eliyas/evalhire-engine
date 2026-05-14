import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Security, Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db

# ── Constants ────────────────────────────────────────────────────────────────

SECRET_KEY  = os.getenv("SECRET_KEY") or secrets.token_hex(32)
ALGORITHM   = "HS256"
TOKEN_EXPIRE_DAYS = 30

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_oauth2_scheme  = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub else None
    except JWTError:
        return None

# ── FastAPI dependencies ──────────────────────────────────────────────────────

def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> None:
    """
    Validates the X-API-Key header against the API_KEY env var.
    If API_KEY is not set, auth is skipped (dev / CI mode).
    """
    expected = os.getenv("API_KEY")
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def get_optional_user(
    token: Optional[str] = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Returns the User ORM object if a valid Bearer token is present, else None."""
    if not token:
        return None
    user_id = decode_token(token)
    if not user_id:
        return None
    from app.db_models import User  # avoid circular import at module level
    return db.query(User).filter(User.id == user_id).first()


def get_current_user(
    token: Optional[str] = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Like get_optional_user but raises 401 if not authenticated."""
    user = get_optional_user(token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

