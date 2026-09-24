"""Bearer-token authentication shared by the native (/api) and OpenAI-compatible (/v1) APIs."""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from app.config.settings import Settings, get_settings


def verify_router_api_key(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Require `Authorization: Bearer <ROUTER_API_KEY>` when ROUTER_API_KEY is configured.

    With no key configured the API stays open (local development). The comparison is
    constant-time so the key can't be recovered by timing responses.
    """
    if not settings.router_api_key:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), settings.router_api_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
