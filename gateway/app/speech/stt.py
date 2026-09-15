"""Whisper ASR Webservice client.

Endpoint/params verified against the real upstream source
(ahmetoner/whisper-asr-webservice `app/webservice.py`, see
speech-stt/README.md): `POST /asr` takes the audio as a multipart field
named `audio_file`, plus query params `encode`, `task`, `language`,
`output`. We request `output=txt` so the response body is just the
plain-text transcript -- no JSON-shape guessing needed.

This is a thin client per the root README's "speech recognition -> Whisper
service, don't reimplement it" rule; there is no local transcription code
here at all.
"""

from __future__ import annotations

import httpx

from app.agents.base import AgentError
from app.config import Settings


class SpeechToText:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        language: str | None = None,
    ) -> str:
        settings = self.settings
        params = {"task": "transcribe", "encode": "true", "output": "txt"}
        effective_language = language or settings.stt_language
        if effective_language:
            params["language"] = effective_language

        url = f"{settings.stt_url.rstrip('/')}/asr"
        try:
            async with httpx.AsyncClient(timeout=settings.stt_timeout_seconds) as client:
                response = await client.post(
                    url,
                    params=params,
                    files={"audio_file": (filename, audio_bytes, content_type)},
                )
        except httpx.HTTPError as exc:
            raise AgentError("STT_UNAVAILABLE", f"Whisper request failed: {exc}") from exc

        if response.status_code != 200:
            raise AgentError(
                "STT_UNAVAILABLE",
                f"Whisper returned HTTP {response.status_code}: {response.text[:200]}",
            )
        return response.text.strip()

    async def check_available(self) -> bool:
        url = f"{self.settings.stt_url.rstrip('/')}/docs"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False
