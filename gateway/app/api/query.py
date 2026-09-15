"""The core orchestration endpoints: text and audio natural-language queries.

This is the "HTTP -> CLI -> MCP -> Plane" path the root README calls the
core of the whole system. Every other endpoint is secondary to this one.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentError
from app.agents.factory import get_agent
from app.api.cancellation import cancel, track
from app.api.deps import get_agent_semaphore, get_db
from app.api.errors import ApiError
from app.api.schemas import (
    AgentInfo,
    AudioQueryResponse,
    AudioRef,
    CancelResponse,
    QueryRequest,
    QueryResponse,
)
from app.config import Settings, get_settings
from app.logging_config import log_event
from app.prompts.builder import build_prompt
from app.security.auth import require_bearer_token
from app.sessions.repository import ConversationRepository
from app.speech.cache import TtsCache
from app.speech.probe import probe_duration_seconds
from app.speech.stt import SpeechToText
from app.speech.tts import TextToSpeech
from app.speech.validation import validate_audio_content_type

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_bearer_token)])


def _require_plane_configured(settings: Settings) -> None:
    if not settings.plane_is_configured():
        raise ApiError(
            "PLANE_UNAVAILABLE",
            "Plane credentials are not configured yet. Complete the Phase 1 "
            "bootstrap (create a workspace, set PLANE_WORKSPACE_SLUG and "
            "PLANE_API_KEY) before asking the assistant anything.",
        )


async def _run_agent(settings: Settings, semaphore: asyncio.Semaphore, prompt: str, request_id: str):
    agent = get_agent(settings)

    async def _execute():
        async with semaphore:
            return await agent.execute(prompt, settings.agent_timeout_seconds)

    task = asyncio.ensure_future(_execute())
    with track(request_id, task):
        try:
            return await task
        except asyncio.CancelledError:
            raise ApiError("AGENT_TIMEOUT", "The request was cancelled.")


async def _maybe_synthesize_for_response(
    settings: Settings, request_id: str, text: str
) -> AudioRef | None:
    try:
        tts = TextToSpeech(settings)
        audio_bytes = await tts.synthesize(text)
    except AgentError as exc:
        log_event(logger, logging.WARNING, "tts_for_query_failed", request_id=request_id, error=str(exc))
        return None
    cache = TtsCache(settings, subdirectory="responses")
    cache.put(request_id, settings.tts_format, audio_bytes)
    return AudioRef(
        available=True,
        url=f"/api/v1/audio/responses/{request_id}",
        mime_type=tts.mime_type(settings.tts_format),
    )


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    semaphore: asyncio.Semaphore = Depends(get_agent_semaphore),
):
    _require_plane_configured(settings)
    request_id = str(uuid.uuid4())
    repo = ConversationRepository(db)
    conversation = await repo.get_or_create(body.conversation_id)
    history = await repo.recent_messages(conversation.id, settings.conversation_context_messages)
    await repo.add_message(conversation.id, "user", body.query)

    prompt = build_prompt(
        settings, body.query, history, now=datetime.now(timezone.utc).isoformat()
    )
    result = await _run_agent(settings, semaphore, prompt, request_id)

    await repo.add_message(
        conversation.id,
        "assistant",
        result.answer,
        metadata={
            "tools_used": result.tools_used,
            "cli": result.cli,
            "model": result.model,
            "reasoning": result.reasoning,
        },
    )

    audio_ref = None
    if body.include_audio:
        audio_ref = await _maybe_synthesize_for_response(settings, request_id, result.answer)

    return QueryResponse(
        request_id=request_id,
        conversation_id=conversation.id,
        query=body.query,
        answer=result.answer,
        agent=AgentInfo(cli=result.cli, model=result.model),
        audio=audio_ref,
        duration_ms=result.duration_ms,
        reasoning=result.reasoning,
    )


@router.post("/query/audio", response_model=AudioQueryResponse)
async def query_audio(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    include_audio: bool = Form(default=False),
    language: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    semaphore: asyncio.Semaphore = Depends(get_agent_semaphore),
):
    _require_plane_configured(settings)
    audio_bytes = await _read_and_validate_audio(file, settings)

    request_id = str(uuid.uuid4())
    stt = SpeechToText(settings)
    transcript = await stt.transcribe(
        audio_bytes,
        filename=file.filename or "audio",
        content_type=file.content_type or "application/octet-stream",
        language=language,
    )
    if not transcript:
        raise ApiError(
            "EMPTY_TRANSCRIPT", "No speech was detected in that recording.", status_code=400
        )

    repo = ConversationRepository(db)
    conversation = await repo.get_or_create(conversation_id)
    history = await repo.recent_messages(conversation.id, settings.conversation_context_messages)
    await repo.add_message(conversation.id, "user", transcript)

    prompt = build_prompt(
        settings, transcript, history, now=datetime.now(timezone.utc).isoformat()
    )
    try:
        result = await _run_agent(settings, semaphore, prompt, request_id)
    except AgentError as exc:
        # STT already succeeded and `transcript` is safely persisted above --
        # never let a downstream agent failure make it look to the client
        # as if nothing was heard at all. See ApiError.extra's docstring.
        raise ApiError(exc.code, exc.message, extra={"transcript": transcript}) from exc
    except ApiError as exc:
        exc.extra = {**exc.extra, "transcript": transcript}
        raise

    await repo.add_message(
        conversation.id,
        "assistant",
        result.answer,
        metadata={
            "tools_used": result.tools_used,
            "cli": result.cli,
            "model": result.model,
            "reasoning": result.reasoning,
        },
    )

    audio_ref = None
    if include_audio:
        audio_ref = await _maybe_synthesize_for_response(settings, request_id, result.answer)

    return AudioQueryResponse(
        request_id=request_id,
        conversation_id=conversation.id,
        transcript=transcript,
        answer=result.answer,
        agent=AgentInfo(cli=result.cli, model=result.model),
        audio=audio_ref,
        reasoning=result.reasoning,
    )


async def _read_and_validate_audio(file: UploadFile, settings: Settings) -> bytes:
    validate_audio_content_type(file.content_type)
    max_bytes = settings.max_audio_size_mb * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise ApiError(
            "AUDIO_TOO_LARGE",
            f"Audio exceeds the {settings.max_audio_size_mb}MB limit.",
        )
    if not data:
        raise ApiError("INVALID_REQUEST", "Empty audio upload.", status_code=400)

    duration = await probe_duration_seconds(data)
    if duration is not None and duration > settings.max_audio_duration_seconds:
        raise ApiError(
            "AUDIO_TOO_LARGE",
            f"Audio exceeds the {settings.max_audio_duration_seconds}s duration limit "
            f"({duration:.0f}s).",
        )
    return data


@router.delete("/requests/{request_id}", response_model=CancelResponse)
async def cancel_request(request_id: str):
    return CancelResponse(cancelled=cancel(request_id))
