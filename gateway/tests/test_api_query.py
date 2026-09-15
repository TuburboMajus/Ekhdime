from app.agents.base import AgentError, AgentResult
from app.config import get_settings


class FakeAgent:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def execute(self, prompt, timeout_seconds):
        if self._error:
            raise self._error
        return self._result

    async def check_available(self):
        return True, "1.0.0"


def _auth():
    return {"Authorization": "Bearer test-token"}


def test_query_happy_path(api_client, monkeypatch, settings):
    fake_result = AgentResult(
        answer="You have 3 projects.",
        cli="copilot",
        model=settings.llm_model,
        duration_ms=100,
        exit_code=0,
        tools_used=["plane.list_projects"],
    )
    monkeypatch.setattr(
        "app.api.query.get_agent", lambda settings: FakeAgent(result=fake_result)
    )

    response = api_client.post(
        "/api/v1/query", json={"query": "list my projects"}, headers=_auth()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "You have 3 projects."
    assert body["agent"]["cli"] == "copilot"
    assert body["audio"] is None
    assert body["conversation_id"]
    assert body["request_id"]


def test_query_response_includes_reasoning_when_present(api_client, monkeypatch, settings):
    fake_result = AgentResult(
        answer="You have 3 projects.",
        cli="copilot",
        model=settings.llm_model,
        duration_ms=100,
        exit_code=0,
        reasoning="The user wants a project list. I'll call list_projects.",
    )
    monkeypatch.setattr("app.api.query.get_agent", lambda settings: FakeAgent(result=fake_result))

    response = api_client.post("/api/v1/query", json={"query": "list my projects"}, headers=_auth())
    body = response.json()
    assert body["reasoning"] == "The user wants a project list. I'll call list_projects."


def test_query_response_reasoning_is_null_when_absent(api_client, monkeypatch, settings):
    fake_result = AgentResult(
        answer="Hello.", cli="copilot", model=settings.llm_model, duration_ms=1, exit_code=0
    )
    monkeypatch.setattr("app.api.query.get_agent", lambda settings: FakeAgent(result=fake_result))

    response = api_client.post("/api/v1/query", json={"query": "hi"}, headers=_auth())
    assert response.json()["reasoning"] is None


def test_query_requires_plane_configured(api_client, monkeypatch, settings):
    unconfigured = settings.model_copy(update={"plane_workspace_slug": "", "plane_api_key": ""})
    api_client.app.dependency_overrides[get_settings] = lambda: unconfigured

    response = api_client.post("/api/v1/query", json={"query": "hi"}, headers=_auth())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PLANE_UNAVAILABLE"


def test_query_maps_agent_timeout_to_504(api_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.query.get_agent",
        lambda settings: FakeAgent(error=AgentError("AGENT_TIMEOUT", "took too long")),
    )

    response = api_client.post("/api/v1/query", json={"query": "hi"}, headers=_auth())
    assert response.status_code == 504
    body = response.json()
    assert body["error"]["code"] == "AGENT_TIMEOUT"
    assert "request_id" in body["error"]


def test_query_requires_auth(api_client):
    response = api_client.post("/api/v1/query", json={"query": "hi"})
    assert response.status_code == 401


def test_query_rejects_empty_query_body(api_client):
    response = api_client.post("/api/v1/query", json={"query": ""}, headers=_auth())
    assert response.status_code == 400


def test_query_persists_conversation_and_reuses_it(api_client, monkeypatch, settings):
    fake_result = AgentResult(
        answer="ok", cli="copilot", model=settings.llm_model, duration_ms=1, exit_code=0
    )
    monkeypatch.setattr(
        "app.api.query.get_agent", lambda settings: FakeAgent(result=fake_result)
    )

    first = api_client.post("/api/v1/query", json={"query": "first"}, headers=_auth())
    conversation_id = first.json()["conversation_id"]

    second = api_client.post(
        "/api/v1/query",
        json={"query": "second", "conversation_id": conversation_id},
        headers=_auth(),
    )
    assert second.json()["conversation_id"] == conversation_id

    detail = api_client.get(f"/api/v1/conversations/{conversation_id}", headers=_auth())
    contents = [m["content"] for m in detail.json()["messages"]]
    assert contents == ["first", "ok", "second", "ok"]


def test_list_conversations_wraps_in_envelope_object(api_client):
    # Matches gateway/API.md exactly: {"conversations": [...]}, not a bare
    # JSON array -- the mobile client depends on this shape.
    created = api_client.post("/api/v1/conversations", json={"title": "Sprint planning"}, headers=_auth())
    assert created.status_code == 201

    response = api_client.get("/api/v1/conversations", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert "conversations" in body
    assert body["conversations"][0]["title"] == "Sprint planning"


def test_cancel_unknown_request_returns_false(api_client):
    response = api_client.delete("/api/v1/requests/does-not-exist", headers=_auth())
    assert response.status_code == 200
    assert response.json() == {"cancelled": False}
