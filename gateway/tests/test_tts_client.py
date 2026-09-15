import time

import httpx
import pytest

from app.agents.base import AgentError
from app.speech.cache import TtsCache, cache_key
from app.speech.tts import TextToSpeech
from tests.conftest import make_settings


class FakeResponse:
    def __init__(self, status_code=200, content=b"", json_data=None, text=""):
        self.status_code = status_code
        self.content = content
        self._json = json_data
        self.text = text

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
        if self._raise_error:
            raise httpx.ConnectError("connection refused")
        return self._response


@pytest.fixture
def settings(tmp_path):
    return make_settings(
        tts_url="http://speech-tts:8880", tts_cache_dir=str(tmp_path / "tts-cache")
    )


async def test_synthesize_returns_audio_bytes(monkeypatch, settings):
    response = FakeResponse(status_code=200, content=b"\xff\xfb\x90\x00fake-mp3")
    monkeypatch.setattr(
        "app.speech.tts.httpx.AsyncClient", lambda **kw: FakeAsyncClient(response=response)
    )

    tts = TextToSpeech(settings)
    audio = await tts.synthesize("hello")
    assert audio == b"\xff\xfb\x90\x00fake-mp3"


async def test_synthesize_picks_voice_matching_text_language(monkeypatch, settings):
    # Regression test for a real incident: French answers were spoken with
    # the English default voice ("catastrophic" pronunciation per the user
    # who heard it) because synthesize() always sent settings.tts_voice
    # regardless of what language `text` was actually in.
    response = FakeResponse(status_code=200, content=b"fake-audio")
    fake_client = FakeAsyncClient(response=response)
    monkeypatch.setattr("app.speech.tts.httpx.AsyncClient", lambda **kw: fake_client)

    tts = TextToSpeech(settings)
    await tts.synthesize(
        "Je n'ai trouve aucun projet dans ce workspace. Dis-moi si tu veux que j'en cree un."
    )
    assert fake_client.last_call[1]["json"]["voice"] == "ff_siwis"


async def test_synthesize_respects_explicit_voice_override(monkeypatch, settings):
    response = FakeResponse(status_code=200, content=b"fake-audio")
    fake_client = FakeAsyncClient(response=response)
    monkeypatch.setattr("app.speech.tts.httpx.AsyncClient", lambda **kw: fake_client)

    tts = TextToSpeech(settings)
    await tts.synthesize("Bonjour tout le monde", voice="am_adam")
    assert fake_client.last_call[1]["json"]["voice"] == "am_adam"


async def test_synthesize_raises_tts_unavailable_on_error(monkeypatch, settings):
    monkeypatch.setattr(
        "app.speech.tts.httpx.AsyncClient", lambda **kw: FakeAsyncClient(raise_error=True)
    )

    tts = TextToSpeech(settings)
    with pytest.raises(AgentError) as exc_info:
        await tts.synthesize("hello")
    assert exc_info.value.code == "TTS_UNAVAILABLE"


async def test_list_voices_flattens_voice_objects(monkeypatch, settings):
    # Verified real shape from a live Kokoro-FastAPI v0.9.0 container: a list
    # of objects, not bare strings -- see speech-tts/README.md.
    response = FakeResponse(
        status_code=200,
        json_data={"voices": [{"id": "af_heart", "name": "af_heart"}, {"id": "af_bella"}]},
    )
    monkeypatch.setattr(
        "app.speech.tts.httpx.AsyncClient", lambda **kw: FakeAsyncClient(response=response)
    )

    tts = TextToSpeech(settings)
    voices, default = await tts.list_voices()
    assert voices == ["af_heart", "af_bella"]
    assert default == settings.tts_voice


async def test_list_voices_falls_back_when_unreachable(monkeypatch, settings):
    monkeypatch.setattr(
        "app.speech.tts.httpx.AsyncClient", lambda **kw: FakeAsyncClient(raise_error=True)
    )

    tts = TextToSpeech(settings)
    voices, default = await tts.list_voices()
    assert len(voices) > 0  # falls back to a static list rather than raising


def test_mime_type_lookup(settings):
    tts = TextToSpeech(settings)
    assert tts.mime_type("mp3") == "audio/mpeg"
    assert tts.mime_type("wav") == "audio/wav"
    assert tts.mime_type("unknown-format") == "application/octet-stream"


# --- TtsCache ---


def test_cache_key_is_deterministic():
    key1 = cache_key("hello", "af_heart", "mp3", 1.0, "kokoro")
    key2 = cache_key("hello", "af_heart", "mp3", 1.0, "kokoro")
    key3 = cache_key("hello", "af_bella", "mp3", 1.0, "kokoro")
    assert key1 == key2
    assert key1 != key3


def test_cache_put_and_get_roundtrip(settings):
    cache = TtsCache(settings)
    cache.put("abc123", "mp3", b"audio-bytes")
    assert cache.get("abc123", "mp3") == b"audio-bytes"


def test_cache_get_missing_returns_none(settings):
    cache = TtsCache(settings)
    assert cache.get("does-not-exist", "mp3") is None


def test_cache_expires_after_ttl(settings):
    settings.tts_cache_ttl_seconds = 0
    cache = TtsCache(settings)
    cache.put("abc123", "mp3", b"audio-bytes")
    time.sleep(0.05)
    assert cache.get("abc123", "mp3") is None


def test_cache_evicts_oldest_when_over_size_limit(settings):
    settings.tts_cache_max_mb = 0  # force eviction on every put
    cache = TtsCache(settings)
    cache.put("first", "mp3", b"x" * 1024)
    cache.put("second", "mp3", b"y" * 1024)
    # The bounded cache must not grow forever -- oldest entries get evicted.
    remaining = list(cache.dir.glob("*"))
    assert len(remaining) <= 1


def test_cache_subdirectory_isolation(settings):
    responses_cache = TtsCache(settings, subdirectory="responses")
    default_cache = TtsCache(settings)
    responses_cache.put("req-1", "mp3", b"response-audio")
    assert default_cache.get("req-1", "mp3") is None
    assert responses_cache.get("req-1", "mp3") == b"response-audio"
