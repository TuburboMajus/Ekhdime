"""Regression tests against the *real* prompt file (prompts/plane-assistant.md),
not the minimal test fixture used by test_prompt_builder.py's templating tests.

Requires prompts/ mounted at /app/prompts (see the root Makefile's test-unit
target, which mirrors gateway/docker-compose.yml's real mount) -- skipped
otherwise rather than failing, so a bare `pytest` run outside that mount
doesn't error on an environment gap unrelated to the code under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.prompts.builder import build_prompt
from tests.conftest import make_settings

REAL_PROMPT_PATH = Path("/app/prompts/plane-assistant.md")

pytestmark = pytest.mark.skipif(
    not REAL_PROMPT_PATH.exists(),
    reason="prompts/ not mounted -- run via `make test-unit`",
)


def _real_prompt_settings(**overrides):
    return make_settings(prompt_path=str(REAL_PROMPT_PATH), **overrides)


def test_prompt_tells_model_duplicate_tool_renderings_are_one_result():
    # Regression test for a real incident: plane-mcp's MCP responses
    # correctly include both a plain-JSON `content` block and a
    # `{"result": ...}`-wrapped `structuredContent` block per the MCP spec
    # (FastMCP's `wrap_result` for non-object return types) -- Copilot CLI's
    # own event log then concatenates both into the model's view as two
    # differently-shaped renderings of the same data. Without this guidance,
    # deepseek-v4-flash treated that as a suspicious inconsistency and
    # amplified into hallucinated tool-call markup (see
    # app/agents/sanitize.py) instead of trusting the result.
    prompt = build_prompt(_real_prompt_settings(), "list all my projects")
    lowered = prompt.lower()
    assert "same data" in lowered or "same result" in lowered
    assert "empty list" in lowered
    assert "double check" in lowered or "double-check" in lowered


def test_prompt_forbids_inventing_tool_call_syntax():
    prompt = build_prompt(_real_prompt_settings(), "list all my projects")
    lowered = prompt.lower()
    assert "tool-call syntax" in lowered or "looks like invoking a tool" in lowered
