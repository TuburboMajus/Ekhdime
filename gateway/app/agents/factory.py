"""Selects the active AgentCLI implementation from `AGENT_CLI`.

This is the only place in the app that branches on which CLI is active --
everything else (app/api/query.py) works purely against the `AgentCLI`
interface, per the root README's "the rest of the application must not care
which implementation is active" rule.

Construction is cheap (each adapter just holds a `Settings` reference), so
this deliberately does not cache instances -- caching by `Settings` would
either require `Settings` to be hashable or silently ignore whatever
`Settings` instance the caller actually passed in (e.g. an overridden one in
tests), which is worse than the cost of a trivial object construction.
"""

from __future__ import annotations

from app.agents.base import AgentCLI
from app.agents.claude import ClaudeAgent
from app.agents.copilot import CopilotAgent
from app.config import Settings, get_settings

_REGISTRY: dict[str, type[AgentCLI]] = {
    "copilot": CopilotAgent,
    "claude": ClaudeAgent,
}


def get_agent(settings: Settings | None = None) -> AgentCLI:
    settings = settings or get_settings()
    return _REGISTRY[settings.agent_cli](settings)
