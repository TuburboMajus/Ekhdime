"""Central, env-driven configuration.

Every knob the rest of the app reads comes from here, and every field here
maps 1:1 to a documented variable in `.env.example`. Nothing in `app/` should
call `os.getenv` directly -- see the root README's "no hard-coded LLM/CLI
assumptions" design rule.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

UNSAFE_DEFAULT_TOKENS = {"change-me", "changeme", "change_me", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Runtime mode ---
    environment: Literal["development", "production"] = "development"

    # --- Gateway ---
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8088
    gateway_api_token: str = "change-me"

    # --- Agent selection ---
    agent_cli: Literal["copilot", "claude"] = "copilot"
    # 180s was too tight for multi-turn tool use (list + follow-up reasoning
    # can legitimately take 2-3 minutes with a slower model) -- observed real
    # queries timing out client-side despite the CLI still working. 300s
    # keeps well within Mobile's queryTimeout (see api_client.dart).
    agent_timeout_seconds: int = 300
    agent_max_concurrent_requests: int = 2
    copilot_bin: str = "copilot"
    claude_bin: str = "claude"

    # --- LLM (generic; adapters translate this into CLI-specific env vars) ---
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/anthropic"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-pro"

    # --- Plane ---
    plane_public_url: str = "http://localhost:8080"
    plane_workspace_slug: str = ""
    plane_api_key: str = ""
    plane_user_email: str = ""
    plane_user_id: str = ""
    # Internal (Docker-network) URL of Plane's API, used only for the
    # infra-level health check in app/plane/health.py -- see design rule 2.2,
    # this is the one place allowed to call Plane's REST API directly.
    plane_internal_base_url: str = "http://api:8000"

    # --- Plane MCP ---
    # Full URL including the header-auth MCP path -- see plane-mcp/README.md.
    plane_mcp_url: str = "http://plane-mcp:8211/http/api-key/mcp"

    # --- Conversations ---
    conversation_context_messages: int = 10
    # NOT `DATABASE_URL` -- that name is already claimed by Plane's own
    # compose file (its Postgres connection string) and this stack merges
    # every component's env vars into one shared root `.env`. Reusing it
    # here silently overwrote Plane's DATABASE_URL with this SQLite URL,
    # crashing Plane's `api`/`migrator` containers on a real full-stack run
    # (`dj_database_url.UnknownSchemeError: sqlite+aiosqlite://`) -- found
    # by actually running `docker compose up` on the complete stack.
    gateway_database_url: str = "sqlite+aiosqlite:////data/gateway.db"

    # --- Audio limits ---
    max_audio_size_mb: int = 25
    max_audio_duration_seconds: int = 300

    # --- Speech-to-text (Whisper ASR Webservice) ---
    stt_url: str = "http://speech-stt:9000"
    stt_engine: str = "faster_whisper"
    stt_model: str = "small"
    stt_language: str = ""
    stt_timeout_seconds: int = 60

    # --- Text-to-speech (Kokoro-FastAPI) ---
    tts_url: str = "http://speech-tts:8880"
    tts_model: str = "kokoro"
    tts_voice: str = "af_heart"
    tts_format: str = "mp3"
    tts_speed: float = 1.0
    tts_timeout_seconds: int = 60
    tts_cache_ttl_seconds: int = 3600
    tts_cache_max_mb: int = 500
    tts_cache_dir: str = "/data/tts-cache"

    # --- Prompts ---
    prompt_path: str = "/app/prompts/plane-assistant.md"

    # --- Logging ---
    log_level: str = "INFO"
    log_request_content: bool = False

    @field_validator("gateway_api_token")
    @classmethod
    def _check_unsafe_token(cls, value: str, info):
        # Only a shape check here; the hard refusal-to-start lives in
        # main.py's startup check, which also knows `environment`. Pydantic
        # validators run per-field and don't reliably see sibling fields in
        # all pydantic-settings versions, so we re-check there deliberately.
        return value

    @property
    def prompt_file(self) -> Path:
        return Path(self.prompt_path)

    def is_unsafe_default_token(self) -> bool:
        return self.gateway_api_token.strip().lower() in UNSAFE_DEFAULT_TOKENS

    def plane_is_configured(self) -> bool:
        return bool(self.plane_workspace_slug and self.plane_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
