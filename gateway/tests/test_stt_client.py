import httpx
import pytest

from app.agents.base import AgentError
from app.speech.stt import SpeechToText
from tests.conftest import make_settings


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        return self._json


class FakeAsyncClient:
    def __init__(self, response=None, raise_error=False, **kwargs):
        self._response = response or FakeResponse()
        self._raise_error = raise_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        if self._raise_error:
            raise httpx.ConnectError("connection refused")
        self.last_call = (url, kwargs)
        return self._response

    async def get(self, url, **kwargs):
        return self._response


@pytest.fixture
def settings():
    return make_settings(stt_url="http://speech-stt:9000", stt_language="")


async def test_transcribe_returns_stripped_text(monkeypatch, settings):
    response = FakeResponse(status_code=200, text="  list my projects  \n")
    monkeypatch.setattr(
        "app.speech.stt.httpx.AsyncClient", lambda **kw: FakeAsyncClient(response=response)
    )

    stt = SpeechToText(settings)
    text = await stt.transcribe(b"fake-audio-bytes", "recording.wav", "audio/wav")
    assert text == "list my projects"


async def test_transcribe_sends_language_when_provided(monkeypatch, settings):
    captured = {}

    class CapturingClient(FakeAsyncClient):
        async def post(self, url, **kwargs):
            captured["params"] = kwargs.get("params")
            captured["files"] = kwargs.get("files")
            return FakeResponse(status_code=200, text="bonjour")

    monkeypatch.setattr("app.speech.stt.httpx.AsyncClient", lambda **kw: CapturingClient())

    stt = SpeechToText(settings)
    await stt.transcribe(b"data", "a.wav", "audio/wav", language="fr")
    assert captured["params"]["language"] == "fr"
    assert captured["files"]["audio_file"][0] == "a.wav"


async def test_transcribe_raises_stt_unavailable_on_non_200(monkeypatch, settings):
    response = FakeResponse(status_code=500, text="internal error")
    monkeypatch.setattr(
        "app.speech.stt.httpx.AsyncClient", lambda **kw: FakeAsyncClient(response=response)
    )

    stt = SpeechToText(settings)
    with pytest.raises(AgentError) as exc_info:
        await stt.transcribe(b"data", "a.wav", "audio/wav")
    assert exc_info.value.code == "STT_UNAVAILABLE"


async def test_transcribe_raises_stt_unavailable_on_connection_error(monkeypatch, settings):
    monkeypatch.setattr(
        "app.speech.stt.httpx.AsyncClient", lambda **kw: FakeAsyncClient(raise_error=True)
    )

    stt = SpeechToText(settings)
    with pytest.raises(AgentError) as exc_info:
        await stt.transcribe(b"data", "a.wav", "audio/wav")
    assert exc_info.value.code == "STT_UNAVAILABLE"
