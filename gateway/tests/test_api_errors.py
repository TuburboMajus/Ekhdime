def _auth():
    return {"Authorization": "Bearer test-token"}


def test_health_is_public_and_returns_ok(api_client):
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_info_is_public(api_client):
    response = api_client.get("/api/v1/info")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    assert "features" in body


def test_health_details_requires_auth(api_client):
    response = api_client.get("/api/v1/health/details")
    assert response.status_code == 401


def test_conversation_not_found_returns_envelope(api_client):
    response = api_client.get("/api/v1/conversations/does-not-exist", headers=_auth())
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]


def test_delete_missing_conversation_is_idempotent(api_client):
    response = api_client.delete("/api/v1/conversations/does-not-exist", headers=_auth())
    assert response.status_code == 204


def test_every_error_response_matches_envelope_shape(api_client):
    # UNAUTHORIZED, INVALID_REQUEST, NOT_FOUND all use the same envelope --
    # spot check the shape holds across different error paths.
    responses = [
        api_client.get("/api/v1/health/details"),  # 401
        api_client.post("/api/v1/query", json={"query": ""}, headers=_auth()),  # 400
        api_client.get("/api/v1/conversations/missing", headers=_auth()),  # 404
    ]
    for response in responses:
        body = response.json()
        assert set(body.keys()) == {"error"}
        assert set(body["error"].keys()) == {"code", "message", "request_id"}


def test_response_includes_request_id_header(api_client):
    response = api_client.get("/api/v1/health")
    assert "X-Request-Id" in response.headers
