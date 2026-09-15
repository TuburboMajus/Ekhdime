from tests.conftest import make_settings


def test_env_var_parsing(monkeypatch):
    monkeypatch.setenv("GATEWAY_PORT", "9999")
    monkeypatch.setenv("AGENT_MAX_CONCURRENT_REQUESTS", "5")
    monkeypatch.setenv("LOG_REQUEST_CONTENT", "true")
    from app.config import Settings

    settings = Settings()
    assert settings.gateway_port == 9999
    assert settings.agent_max_concurrent_requests == 5
    assert settings.log_request_content is True


def test_unsafe_default_token_detected():
    settings = make_settings(gateway_api_token="change-me")
    assert settings.is_unsafe_default_token() is True

    settings = make_settings(gateway_api_token="")
    assert settings.is_unsafe_default_token() is True

    settings = make_settings(gateway_api_token="a-real-strong-token")
    assert settings.is_unsafe_default_token() is False


def test_plane_is_configured():
    settings = make_settings(plane_workspace_slug="", plane_api_key="")
    assert settings.plane_is_configured() is False

    settings = make_settings(plane_workspace_slug="ws", plane_api_key="key")
    assert settings.plane_is_configured() is True


def test_worst_case_audio_pipeline_fits_in_mobile_query_timeout():
    # Regression test for a real incident: POST /query/audio runs STT ->
    # agent -> (optional) TTS sequentially with no overall per-request
    # deadline, so the worst case a client can legitimately wait for is the
    # *sum* of all three stage timeouts, not just agent_timeout_seconds.
    # Found live: stt(60) + agent(300) + tts(60) = 420s against a 360s
    # mobile queryTimeout -- any voice query with audio playback enabled
    # (the default use case) was liable to time out client-side while the
    # server was still legitimately working.
    #
    # MOBILE_QUERY_TIMEOUT_SECONDS mirrors `queryTimeout` in
    # mobile/lib/api/api_client.dart -- there's no shared config between the
    # two codebases, so keep them in sync by hand. If you bump
    # agent/stt/tts_timeout_seconds, this test will fail until you also
    # raise queryTimeout there.
    MOBILE_QUERY_TIMEOUT_SECONDS = 480

    settings = make_settings()
    worst_case = (
        settings.stt_timeout_seconds
        + settings.agent_timeout_seconds
        + settings.tts_timeout_seconds
    )
    assert worst_case < MOBILE_QUERY_TIMEOUT_SECONDS, (
        f"worst-case /query/audio pipeline ({worst_case}s) must stay under "
        f"mobile's queryTimeout ({MOBILE_QUERY_TIMEOUT_SECONDS}s) -- raise "
        "queryTimeout in mobile/lib/api/api_client.dart to match"
    )
