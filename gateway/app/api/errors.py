"""The error envelope contract from API.md, enforced in one place.

`{"error": {"code": ..., "message": ..., "request_id": ...}}` for every
non-2xx response -- never a bare FastAPI/Starlette default error body.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.base import AgentError

logger = logging.getLogger(__name__)

_DEFAULT_STATUS_BY_CODE = {
    "UNAUTHORIZED": 401,
    "INVALID_REQUEST": 400,
    "NOT_FOUND": 404,
    "AUDIO_TOO_LARGE": 413,
    "STT_UNAVAILABLE": 503,
    "TTS_UNAVAILABLE": 503,
    "MCP_UNAVAILABLE": 503,
    "PLANE_UNAVAILABLE": 503,
    "AGENT_UNAVAILABLE": 503,
    "AGENT_TIMEOUT": 504,
    "AGENT_INVALID_RESPONSE": 502,
    "EMPTY_TRANSCRIPT": 400,
    "LLM_AUTHENTICATION_ERROR": 502,
    "LLM_RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
}


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int | None = None,
        extra: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code or _DEFAULT_STATUS_BY_CODE.get(code, 500)
        # Merged into the top-level response body alongside "error" --
        # e.g. `/query/audio` attaches the already-transcribed `transcript`
        # here when the *agent* step fails after STT succeeded, so the
        # client can still show what the user said instead of losing it
        # entirely behind a bare error (see app/api/query.py).
        self.extra = extra or {}


def _envelope(code: str, message: str, request_id: str, extra: dict | None = None) -> dict:
    return {
        "error": {"code": code, "message": message, "request_id": request_id},
        **(extra or {}),
    }


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, _request_id(request), exc.extra),
        )

    @app.exception_handler(AgentError)
    async def agent_error_handler(request: Request, exc: AgentError):
        status_code = _DEFAULT_STATUS_BY_CODE.get(exc.code, 500)
        return JSONResponse(
            status_code=status_code,
            content=_envelope(exc.code, exc.message, _request_id(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content=_envelope("INVALID_REQUEST", str(exc), _request_id(request)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "INVALID_REQUEST"
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), _request_id(request)),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception", extra={"fields": {"path": request.url.path}})
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "An unexpected error occurred.", _request_id(request)),
        )
