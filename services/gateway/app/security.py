"""Service-to-service authentication: every /v1 call must carry the shared token (env GATEWAY_SERVICE_TOKEN)."""
import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException

TOKEN_ENV = "GATEWAY_SERVICE_TOKEN"
MIN_TOKEN_CHARS = 32


class ServiceTokenError(RuntimeError):
    """The expected token is missing or too short."""


def load_service_token() -> str:
    token = os.environ.get(TOKEN_ENV, "")
    if len(token) < MIN_TOKEN_CHARS:
        raise ServiceTokenError(f"{TOKEN_ENV} must be set and at least {MIN_TOKEN_CHARS} characters")
    return token


def token_matches(presented: str | None, expected: str) -> bool:
    if presented is None:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def require_service_token(x_service_token: Annotated[str | None, Header()] = None) -> None:
    """FastAPI dependency. Not configured -> 503 (refuse everything); wrong or missing -> 401."""
    try:
        expected = load_service_token()
    except ServiceTokenError:
        raise HTTPException(status_code=503, detail=["service authentication is not configured"]) from None
    if not token_matches(x_service_token, expected):
        raise HTTPException(status_code=401, detail=["invalid service token"])
