import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.errors import register_exception_handlers
from app.config import get_settings
from app.security.auth import require_bearer_token


@pytest.fixture
def client(settings):
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get("/protected", dependencies=[Depends(require_bearer_token)])
    def protected():
        return {"ok": True}

    return TestClient(app)


def test_rejects_missing_authorization_header(client):
    response = client.get("/protected")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "request_id" in body["error"]


def test_rejects_malformed_authorization_header(client):
    response = client.get("/protected", headers={"Authorization": "Basic abc"})
    assert response.status_code == 401


def test_rejects_wrong_token(client):
    response = client.get("/protected", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_accepts_correct_token(client):
    response = client.get("/protected", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
