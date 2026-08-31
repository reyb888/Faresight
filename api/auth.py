from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
import os

API_KEY_NAME = "x-api-key"
_api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(
    api_key: str = Depends(_api_key_header),
) -> str:
    valid_keys = os.environ.get("API_KEYS", "").split(",")
    valid_keys = [k.strip() for k in valid_keys if k.strip()]
    
    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key


def require_api_key(
    api_key: str = Depends(_api_key_header),
) -> str:
    valid_keys = os.environ.get("API_KEYS", "").split(",")
    valid_keys = [k.strip() for k in valid_keys if k.strip()]
    
    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key


def get_api_key_optional(
    api_key: str = Depends(_api_key_header),
) -> Optional[str]:
    valid_keys = os.environ.get("API_KEYS", "").split(",")
    valid_keys = [k.strip() for k in valid_keys if k.strip()]
    
    if api_key in valid_keys:
        return api_key
    return None