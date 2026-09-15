"""Exercises app/main.py's lifespan directly, including branches the
`api_client` fixture's always-configured settings don't reach (e.g. Plane
not yet bootstrapped) -- a real container run with Plane unconfigured once
crashed here (`log_event() got multiple values for argument 'message'`)
because this branch had no test coverage; this file exists so that can't
regress silently again.
"""

from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import _DEFAULT_OVERRIDES


def test_starts_successfully_when_plane_not_configured(tmp_path, monkeypatch):
    for key, value in _DEFAULT_OVERRIDES.items():
        monkeypatch.setenv(key.upper(), str(value))
    monkeypatch.setenv("GATEWAY_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path / "tts-cache"))
    monkeypatch.setenv("PLANE_WORKSPACE_SLUG", "")
    monkeypatch.setenv("PLANE_API_KEY", "")
    get_settings.cache_clear()

    from app.main import create_app

    app = create_app()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
            assert response.status_code == 200
    finally:
        get_settings.cache_clear()
