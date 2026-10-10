from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
import hmac
import os

API_KEY_NAME = "x-api-key"
_api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Placeholder values that must never be accepted as real credentials.
_PLACEHOLDER_KEYS = {"your-api-key-here", "changeme", "test-key"}


def _get_valid_keys() -> list[str]:
    raw = os.environ.get("API_KEYS", "")
    return [
        k.strip()
        for k in raw.split(",")
        if k.strip() and k.strip().lower() not in _PLACEHOLDER_KEYS
    ]


def require_api_key(
    api_key: str = Depends(_api_key_header),
) -> str:
    valid_keys = _get_valid_keys()
    # Fail closed: if no keys are configured the endpoint is unreachable rather
    # than wide open. Silently allowing every request is how this leaked.
    if not valid_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured on this deployment",
        )
    # Compare every candidate so response time does not leak the key prefix.
    if not api_key or not any(
        hmac.compare_digest(api_key, candidate) for candidate in valid_keys
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key


def get_api_key(
    api_key: str = Depends(_api_key_header),
) -> str:
    return require_api_key(api_key)