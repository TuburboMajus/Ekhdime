"""Loads and renders `prompts/plane-assistant.md`.

Per the root README's prompt-architecture rule: the system prompt lives in an
editable Markdown/Jinja2 file, not in Python source, and is mounted
read-only into the container (see gateway/docker-compose.yml) so it can be
edited without rebuilding the image.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, Template

from app.config import Settings
from app.sessions.models import Message

_env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)


def _load_template(path: Path) -> Template:
    return _env.from_string(path.read_text(encoding="utf-8"))


def format_history(messages: list[Message]) -> str:
    lines = []
    for message in messages:
        speaker = "User" if message.role == "user" else "Assistant"
        lines.append(f"{speaker}: {message.content}")
    return "\n".join(lines)


def build_prompt(
    settings: Settings,
    query: str,
    history: list[Message] | None = None,
    now: str | None = None,
) -> str:
    template = _load_template(settings.prompt_file)
    user_identity = settings.plane_user_email or settings.plane_user_id or ""
    return template.render(
        user_query=query,
        user_identity=user_identity,
        current_datetime=now or "",
        conversation_history=format_history(history) if history else "",
    ).strip()
