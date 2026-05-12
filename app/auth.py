import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> None:
    """
    Validates the X-API-Key header against the API_KEY environment variable.
    If API_KEY is not set, auth is skipped (development / local mode).
    """
    expected = os.getenv("API_KEY")
    if not expected:
        return  # Auth disabled — no API_KEY configured
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
