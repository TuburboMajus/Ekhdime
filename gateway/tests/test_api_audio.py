import io

from app.agents.base import AgentError
from app.speech.stt import SpeechToText
from app.speech.tts import TextToSpeech


def _auth():
    return {"Authorization": "Bearer test-token"}


class _FakeAgent:
    def __init__(self, result=None, error: AgentError | None = None):
        self._result = result
        self._error = error

    async def execute(self, prompt, timeout_seconds):
        if self._error is not None:
            raise self._error
        return self._result

    async def check_available(self):
        return True, "1.0.0"


def test_query_audio_happy_path(api_client, monkeypatch, settings):
    from app.agents.base import AgentResult

    async def fake_transcribe(self, audio_bytes, filename, content_type, language=None):
        return "What should I work on now?"

    monkeypatch.setattr(SpeechToText, "transcribe", fake_transcribe)

    fake_result = AgentResult(
        answer="Start with ABC-42.",
        cli="copilot",
        model=settings.llm_model,
        duration_ms=50,
        exit_code=0,
    )
    monkeypatch.setattr("app.api.query.get_agent", lambda settings: _FakeAgent(fake_result))

    files = {"file": ("recording.wav", io.BytesIO(b"fake-audio-bytes"), "audio/wav")}
    response = api_client.post("/api/v1/query/audio", files=files, headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "What should I work on now?"
    assert body["answer"] == "Start with ABC-42."
    assert body["agent"]["cli"] == "copilot"


def test_query_audio_accepts_generic_octet_stream(api_client, monkeypatch, settings):
    # This is what the mobile app actually sends (Dart's `http` package
    # defaults to this when no content type is set -- see
    # app/speech/validation.py). A real device recording was rejected here
    # before this was fixed.
    from app.agents.base import AgentResult

    async def fake_transcribe(self, audio_bytes, filename, content_type, language=None):
        return "list all my projects"

    monkeypatch.setattr(SpeechToText, "transcribe", fake_transcribe)
    monkeypatch.setattr(
        "app.api.query.get_agent",
        lambda settings: _FakeAgent(
            AgentResult(answer="ok", cli="copilot", model=settings.llm_model, duration_ms=1, exit_code=0)
        ),
    )

    files = {"file": ("recording.m4a", io.BytesIO(b"fake-audio-bytes"), "application/octet-stream")}
    response = api_client.post("/api/v1/query/audio", files=files, headers=_auth())
    assert response.status_code == 200


def test_query_audio_rejects_unsupported_content_type(api_client):
    files = {"file": ("recording.txt", io.BytesIO(b"not audio"), "text/plain")}
    response = api_client.post("/api/v1/query/audio", files=files, headers=_auth())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_query_audio_rejects_oversized_upload(api_client, settings, monkeypatch):
    monkeypatch.setattr(settings, "max_audio_size_mb", 0)
    files = {"file": ("recording.wav", io.BytesIO(b"x" * 1024), "audio/wav")}
    response = api_client.post("/api/v1/query/audio", files=files, headers=_auth())
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "AUDIO_TOO_LARGE"


def test_query_audio_reports_empty_transcript_distinctly(api_client, monkeypatch):
    # Regression test: this used to be a generic INVALID_REQUEST ("Whisper
    # returned an empty transcript"), which reads to a user as "your
    # request was malformed" rather than "we didn't catch any speech" --
    # see gateway/API.md's EMPTY_TRANSCRIPT entry and the mobile-side
    # friendly message for it.
    async def fake_transcribe(self, audio_bytes, filename, content_type, language=None):
        return ""

    monkeypatch.setattr(SpeechToText, "transcribe", fake_transcribe)

    files = {"file": ("recording.m4a", io.BytesIO(b"fake-audio-bytes"), "audio/mp4")}
    response = api_client.post("/api/v1/query/audio", files=files, headers=_auth())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_TRANSCRIPT"
    assert "transcript" not in response.json()


def test_query_audio_agent_failure_still_returns_transcript(api_client, monkeypatch, settings):
    # Regression test for a real gap: STT can succeed and get persisted to
    # conversation history while the *agent* step fails afterward -- without
    # this, the client had no way to know what the user actually said,
    # since AudioQueryResponse (the success schema) is never returned and
    # the plain error envelope carried no transcript at all.
    async def fake_transcribe(self, audio_bytes, filename, content_type, language=None):
        return "list all my projects"

    monkeypatch.setattr(SpeechToText, "transcribe", fake_transcribe)
    monkeypatch.setattr(
        "app.api.query.get_agent",
        lambda settings: _FakeAgent(error=AgentError("AGENT_INVALID_RESPONSE", "leaked tool syntax")),
    )

    files = {"file": ("recording.m4a", io.BytesIO(b"fake-audio-bytes"), "audio/mp4")}
    response = api_client.post("/api/v1/query/audio", files=files, headers=_auth())
    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "AGENT_INVALID_RESPONSE"
    assert body["transcript"] == "list all my projects"


def test_query_audio_rejects_empty_upload(api_client):
    files = {"file": ("recording.wav", io.BytesIO(b""), "audio/wav")}
    response = api_client.post("/api/v1/query/audio", files=files, headers=_auth())
    assert response.status_code == 400


def test_stt_requires_auth(api_client):
    files = {"file": ("recording.wav", io.BytesIO(b"x" * 10), "audio/wav")}
    response = api_client.post("/api/v1/stt", files=files)
    assert response.status_code == 401


def test_tts_returns_audio_bytes_and_caches(api_client, monkeypatch):
    calls = {"count": 0}

    async def fake_synthesize(self, text, voice=None, audio_format=None, speed=None):
        calls["count"] += 1
        return b"fake-mp3-bytes"

    monkeypatch.setattr(TextToSpeech, "synthesize", fake_synthesize)

    body = {"text": "hello", "voice": None, "format": "mp3", "speed": 1.0}
    first = api_client.post("/api/v1/tts", json=body, headers=_auth())
    assert first.status_code == 200
    assert first.content == b"fake-mp3-bytes"
    assert first.headers["content-type"] == "audio/mpeg"

    second = api_client.post("/api/v1/tts", json=body, headers=_auth())
    assert second.content == b"fake-mp3-bytes"

    # Identical (text, voice, format, speed) should hit the cache on the
    # second call rather than calling the TTS engine again.
    assert calls["count"] == 1


def test_tts_voices_endpoint(api_client, monkeypatch):
    async def fake_list_voices(self):
        return ["af_heart", "af_bella"], "af_heart"

    monkeypatch.setattr(TextToSpeech, "list_voices", fake_list_voices)

    response = api_client.get("/api/v1/tts/voices", headers=_auth())
    assert response.status_code == 200
    assert response.json() == {"voices": ["af_heart", "af_bella"], "default": "af_heart"}


def test_audio_response_not_found(api_client):
    response = api_client.get("/api/v1/audio/responses/does-not-exist", headers=_auth())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
