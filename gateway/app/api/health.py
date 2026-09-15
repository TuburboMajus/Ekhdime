from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.factory import get_agent
from app.config import Settings, get_settings
from app.plane.health import check_plane, check_plane_mcp
from app.security.auth import require_bearer_token
from app.speech.stt import SpeechToText
from app.speech.tts import TextToSpeech

router = APIRouter(tags=["health"])

SERVER_VERSION = "0.1.0"


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/info")
async def info():
    return {
        "server_version": SERVER_VERSION,
        "api_version": "v1",
        "features": {
            "stt": True,
            "tts": True,
            "conversations": True,
            "request_cancellation": True,
        },
    }


@router.get("/health/details", dependencies=[Depends(require_bearer_token)])
async def health_details(settings: Settings = Depends(get_settings)):
    plane_ok = await check_plane(settings)
    mcp_ok = await check_plane_mcp(settings)
    stt_ok = await SpeechToText(settings).check_available()
    tts_ok = await TextToSpeech(settings).check_available()
    agent_ok, _ = await get_agent(settings).check_available()

    def status(ok: bool) -> str:
        return "ok" if ok else "error"

    return {
        "gateway": "ok",
        "plane": status(plane_ok),
        "plane_mcp": status(mcp_ok),
        "stt": status(stt_ok),
        "tts": status(tts_ok),
        "agent_cli": {"status": status(agent_ok), "type": settings.agent_cli},
    }
