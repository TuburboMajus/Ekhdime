"""The AgentCLI abstraction.

Nothing outside `app/agents/` should know whether Copilot or Claude is
running -- see the root README's "gateway must invoke a CLI agent" and
"CLI output normalization" design rules. `app/api/query.py` only ever talks
to an `AgentCLI` and receives back an `AgentResult`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class AgentError(Exception):
    """Raised by an AgentCLI implementation; `code` matches API.md's error table."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AgentResult:
    answer: str
    cli: str
    model: str
    duration_ms: int
    exit_code: int
    tools_used: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # The model's chain-of-thought/reasoning trace, kept separate from
    # `answer` so callers can render it as a collapsed-by-default "Thinking"
    # section (like Claude.ai/ChatGPT) instead of mixing it into the visible
    # response. None when the model/CLI didn't produce one for this turn.
    reasoning: str | None = None


class AgentCLI(ABC):
    """One implementation per supported CLI (Copilot, Claude, ...)."""

    name: str

    @abstractmethod
    async def check_available(self) -> tuple[bool, str]:
        """Run the CLI's --version (or equivalent) check.

        Returns (is_available, version_or_error_string).
        """

    @abstractmethod
    async def execute(self, prompt: str, timeout_seconds: int) -> AgentResult:
        """Run one prompt to completion (or raise AgentError)."""
