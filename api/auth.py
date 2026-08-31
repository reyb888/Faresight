from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from typing import Optional
import os

API_KEY_NAME = "x-api-key"
_api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def _get_valid_keys() -> list[str]:
    raw = os.environ.get("API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip() and k.strip() != "your-api-key-here"]


def require_api_key(
    api_key: str = Depends(_api_key_header),
) -> Optional[str]:
    valid_keys = _get_valid_keys()
    if not valid_keys:
        return None
    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key


def get_api_key(
    api_key: str = Depends(_api_key_header),
) -> Optional[str]:
    return require_api_key(api_key)