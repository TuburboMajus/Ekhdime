"""Standalone speech endpoints that don't touch the agent/Plane at all:
transcription-only (`/stt`), synthesis (`/tts`, `/tts/voices`), and fetching
previously-synthesized query audio (`/audio/responses/{id}`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.api.errors import ApiError
from app.api.schemas import SttResponse, TtsRequest, VoicesResponse
from app.config import Settings, get_settings
from app.security.auth import require_bearer_token
from app.speech.cache import TtsCache, cache_key
from app.speech.stt import SpeechToText
from app.speech.tts import TextToSpeech
from app.speech.validation import validate_audio_content_type

router = APIRouter(dependencies=[Depends(require_bearer_token)])


@router.post("/stt", response_model=SttResponse)
async def stt(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
):
    validate_audio_content_type(file.content_type)
    data = await file.read()
    max_bytes = settings.max_audio_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ApiError("AUDIO_TOO_LARGE", f"Audio exceeds the {settings.max_audio_size_mb}MB limit.")
    if not data:
        raise ApiError("INVALID_REQUEST", "Empty audio upload.", status_code=400)

    text = await SpeechToText(settings).transcribe(
        data,
        filename=file.filename or "audio",
        content_type=file.content_type or "application/octet-stream",
        language=language,
    )
    return SttResponse(text=text)


@router.post("/tts")
async def tts(body: TtsRequest, settings: Settings = Depends(get_settings)):
    engine = TextToSpeech(settings)
    voice = body.voice or settings.tts_voice
    key = cache_key(body.text, voice, body.format, body.speed, settings.tts_model)
    cache = TtsCache(settings)

    cached = cache.get(key, body.format)
    if cached is not None:
        return Response(content=cached, media_type=engine.mime_type(body.format))

    audio_bytes = await engine.synthesize(
        body.text, voice=voice, audio_format=body.format, speed=body.speed
    )
    cache.put(key, body.format, audio_bytes)
    return Response(content=audio_bytes, media_type=engine.mime_type(body.format))


@router.get("/tts/voices", response_model=VoicesResponse)
async def tts_voices(settings: Settings = Depends(get_settings)):
    voices, default = await TextToSpeech(settings).list_voices()
    return VoicesResponse(voices=voices, default=default)


@router.get("/audio/responses/{response_id}")
async def audio_response(response_id: str, settings: Settings = Depends(get_settings)):
    cache = TtsCache(settings, subdirectory="responses")
    data = cache.get(response_id, settings.tts_format)
    if data is None:
        raise ApiError("NOT_FOUND", "Audio response not found or expired.", status_code=404)
    engine = TextToSpeech(settings)
    return Response(content=data, media_type=engine.mime_type(settings.tts_format))
