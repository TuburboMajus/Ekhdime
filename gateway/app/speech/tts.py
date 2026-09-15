"""Kokoro-FastAPI client (OpenAI-compatible `/v1/audio/speech`).

Thin client only -- per the root README's "speech generation -> Kokoro,
don't reimplement it" rule. The exact voice list endpoint is Kokoro-specific
(not part of the OpenAI spec it otherwise mirrors); see
speech-tts/README.md for the verified path. If that endpoint is unreachable
we fall back to a small static list rather than failing the whole settings
screen in the mobile app.
"""

from __future__ import annotations

import httpx

from app.agents.base import AgentError
from app.config import Settings
from app.speech.language import voice_for_text

_FALLBACK_VOICES = ["af_heart", "af_bella", "am_adam"]

_FORMAT_TO_MIME = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "opus": "audio/opus",
    "flac": "audio/flac",
    "aac": "audio/aac",
    "pcm": "audio/pcm",
}


class TextToSpeech:
    def __init__(self, settings: Settings):
        self.settings = settings

    def mime_type(self, audio_format: str) -> str:
        return _FORMAT_TO_MIME.get(audio_format, "application/octet-stream")

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str | None = None,
        speed: float | None = None,
    ) -> bytes:
        settings = self.settings
        payload = {
            "model": settings.tts_model,
            "input": text,
            # An explicit `voice` (from the standalone /tts endpoint) always
            # wins; otherwise pick a voice matching the text's own detected
            # language rather than always using settings.tts_voice -- see
            # app/speech/language.py.
            "voice": voice or voice_for_text(text, settings.tts_voice),
            "response_format": audio_format or settings.tts_format,
            "speed": speed or settings.tts_speed,
        }
        url = f"{settings.tts_url.rstrip('/')}/v1/audio/speech"
        try:
            async with httpx.AsyncClient(timeout=settings.tts_timeout_seconds) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise AgentError("TTS_UNAVAILABLE", f"Kokoro request failed: {exc}") from exc

        if response.status_code != 200:
            raise AgentError(
                "TTS_UNAVAILABLE",
                f"Kokoro returned HTTP {response.status_code}: {response.text[:200]}",
            )
        return response.content

    async def list_voices(self) -> tuple[list[str], str]:
        """`GET /v1/audio/voices`. Verified against a live Kokoro-FastAPI
        v0.9.0 container: the response is `{"voices": [{"id": "af_heart",
        "name": "af_heart", ...}, ...]}` -- a list of objects, not bare
        strings -- so each entry is reduced to its `id` here to match this
        gateway's own documented `{"voices": [str, ...]}` contract."""
        settings = self.settings
        url = f"{settings.tts_url.rstrip('/')}/v1/audio/voices"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    raw_voices = data.get("voices") or data.get("data") or []
                    voices = [
                        v.get("id") or v.get("name") if isinstance(v, dict) else v
                        for v in raw_voices
                    ]
                    voices = [v for v in voices if v]
                    if voices:
                        return voices, settings.tts_voice
        except (httpx.HTTPError, ValueError):
            pass
        return _FALLBACK_VOICES, settings.tts_voice

    async def check_available(self) -> bool:
        url = f"{self.settings.tts_url.rstrip('/')}/health"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                return response.status_code < 500
        except httpx.HTTPError:
            return False
