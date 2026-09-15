"""Bearer-token authentication.

MVP auth per the root README: one static, strong, random token shared with
the mobile app. `GET /api/v1/health` and `GET /api/v1/info` are the only
endpoints that skip this dependency (see app/api/health.py).
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header

from app.api.errors import ApiError
from app.config import Settings, get_settings


async def require_bearer_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(
            "UNAUTHORIZED", "Missing or malformed Authorization header", status_code=401
        )
    token = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(token, settings.gateway_api_token):
        raise ApiError("UNAUTHORIZED", "Invalid bearer token", status_code=401)
