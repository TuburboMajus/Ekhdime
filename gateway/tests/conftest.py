from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings

PROMPT_FIXTURE = Path(__file__).parent / "fixtures" / "test-prompt.md"

_DEFAULT_OVERRIDES = dict(
    environment="development",
    gateway_api_token="test-token",
    agent_cli="copilot",
    llm_provider="deepseek",
    llm_base_url="https://api.deepseek.com/anthropic",
    llm_api_key="test-llm-key",
    llm_model="deepseek-v4-pro",
    plane_workspace_slug="test-workspace",
    plane_api_key="test-plane-key",
    plane_user_email="user@example.com",
    plane_mcp_url="http://plane-mcp:8211/http/api-key/mcp",
    prompt_path=str(PROMPT_FIXTURE),
    agent_timeout_seconds=5,
    agent_max_concurrent_requests=2,
    conversation_context_messages=10,
)


def make_settings(**overrides) -> Settings:
    defaults = dict(_DEFAULT_OVERRIDES, gateway_database_url="sqlite+aiosqlite:///:memory:")
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def settings(tmp_path) -> Settings:
    # A real temp-file DB rather than sqlite's `:memory:` -- an in-memory
    # DB is per-connection, and SQLAlchemy's async pool can open more than
    # one connection, which would make writes on one connection invisible
    # to reads on another. tts_cache_dir is similarly redirected away from
    # its `/data/...` default, which isn't writable outside the container.
    return make_settings(
        gateway_database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        tts_cache_dir=str(tmp_path / "tts-cache"),
    )


@pytest.fixture
async def db_engine(settings):
    from app.sessions import repository

    engine = repository.init_engine(settings.gateway_database_url)
    await repository.create_all()
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    from app.sessions import repository

    async with repository.session() as session:
        yield session


@pytest.fixture
def api_client(settings, monkeypatch):
    """A TestClient wired so *every* path that reads settings -- route-level
    `Depends(get_settings)` AND app/main.py's lifespan, which (deliberately,
    see its docstring) reads the global settings singleton directly rather
    than through DI -- agree on the same `Settings` instance. Setting env
    vars and clearing the lru_cache keeps both in sync; overriding only the
    FastAPI dependency would leave the lifespan pointed at a different
    (real) database.
    """
    for key, value in _DEFAULT_OVERRIDES.items():
        monkeypatch.setenv(key.upper(), str(value))
    monkeypatch.setenv("GATEWAY_DATABASE_URL", settings.gateway_database_url)
    monkeypatch.setenv("TTS_CACHE_DIR", settings.tts_cache_dir)
    get_settings.cache_clear()

    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
