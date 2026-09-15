"""FastAPI application factory and startup validation.

Per the root README section 47: refuse to start with an unsafe default
`GATEWAY_API_TOKEN` outside development mode, rather than silently running
an insecure gateway.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import audio, health, query, sessions
from app.api.errors import register_exception_handlers
from app.config import Settings, get_settings
from app.logging_config import configure_logging, log_event
from app.sessions import repository

logger = logging.getLogger(__name__)


def _validate_startup_safety(settings: Settings) -> None:
    if settings.environment == "production" and settings.is_unsafe_default_token():
        raise RuntimeError(
            "GATEWAY_API_TOKEN is unset or a known-unsafe default "
            "('change-me'/empty). Refusing to start with ENVIRONMENT=production. "
            "Generate a strong token (e.g. `openssl rand -hex 32`) and set it "
            "in .env before starting the gateway."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    _validate_startup_safety(settings)

    repository.init_engine(settings.gateway_database_url)
    await repository.create_all()

    log_event(
        logger,
        logging.INFO,
        "gateway_started",
        agent_cli=settings.agent_cli,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        plane_configured=settings.plane_is_configured(),
    )
    if not settings.plane_is_configured():
        log_event(
            logger,
            logging.WARNING,
            "plane_not_configured",
            detail=(
                "PLANE_WORKSPACE_SLUG/PLANE_API_KEY are not set. Health checks "
                "will report plane=error and /query will return PLANE_UNAVAILABLE "
                "until Phase 1 bootstrap is complete (see plane/README.md)."
            ),
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Plane Assistant Gateway",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url="/redoc" if settings.environment == "development" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    register_exception_handlers(app)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(query.router, prefix="/api/v1")
    app.include_router(audio.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")

    return app


app = create_app()
