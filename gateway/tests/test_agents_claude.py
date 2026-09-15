import asyncio
import json

import pytest

from app.agents.base import AgentError
from app.agents.claude import ClaudeAgent
from tests.conftest import make_settings
from tests.test_agents_copilot import FakeProcess


def _ndjson(*events) -> bytes:
    return ("\n".join(json.dumps(e) for e in events)).encode()


@pytest.fixture
def settings():
    return make_settings(agent_cli="claude")


async def test_execute_builds_expected_command(monkeypatch, settings):
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        stdout = _ndjson(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "You have 3 projects."}]},
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": "You have 3 projects."},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    result = await agent.execute("list my projects", timeout_seconds=5)

    assert result.answer == "You have 3 projects."
    assert result.cli == "claude"

    args = captured["args"]
    assert args[0] == "claude"
    assert "-p" in args and "list my projects" in args
    assert "--strict-mcp-config" in args
    assert "--mcp-config" in args
    assert "--allowedTools" in args and "mcp__plane__*" in args
    assert "--tools" in args
    tools_idx = args.index("--tools")
    assert args[tools_idx + 1] == ""  # built-in tools fully disabled
    assert "--permission-prompts" in args and "none" in args
    assert "--dangerously-skip-permissions" not in args  # least-privilege, not blanket bypass

    env = captured["env"]
    assert env["ANTHROPIC_BASE_URL"] == settings.llm_base_url
    assert env["ANTHROPIC_AUTH_TOKEN"] == settings.llm_api_key
    assert env["ANTHROPIC_MODEL"] == settings.llm_model
    assert "ANTHROPIC_API_KEY" not in env


async def test_execute_extracts_mcp_tool_calls(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "mcp__plane__list_projects", "input": {}},
                        {"type": "text", "text": "Here you go."},
                    ]
                },
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": "Here you go."},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    result = await agent.execute("hi", timeout_seconds=5)
    assert result.tools_used == ["mcp__plane__list_projects"]
    assert result.answer == "Here you go."


async def test_execute_extracts_reasoning_separately_from_answer(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "I should call list_projects."},
                        {"type": "text", "text": "You have 3 projects."},
                    ]
                },
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": "You have 3 projects."},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    result = await agent.execute("list my projects", timeout_seconds=5)
    assert result.answer == "You have 3 projects."
    assert result.reasoning == "I should call list_projects."


async def test_execute_reasoning_is_none_when_absent(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello."}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": "Hello."},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    result = await agent.execute("hi", timeout_seconds=5)
    assert result.reasoning is None


async def test_execute_raises_mcp_unavailable_on_needs_auth_even_with_answer_text(
    monkeypatch, settings
):
    # Same regression scenario as the Copilot adapter's equivalent test --
    # see gateway/app/plane/mcp.py's module docstring for the real incident
    # this guards against.
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {
                "type": "system",
                "subtype": "init",
                "mcp_servers": [{"name": "plane", "status": "needs-auth"}],
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "I tried a filesystem tool."}]},
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": "I tried a filesystem tool."},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("list my projects", timeout_seconds=5)
    assert exc_info.value.code == "MCP_UNAVAILABLE"


async def test_execute_raises_invalid_response_on_leaked_tool_syntax(monkeypatch, settings):
    # Same regression scenario as the Copilot adapter's equivalent test:
    # leaked DSML-style pseudo-tool-call markup in the final answer text
    # must never reach the user as if it were a grounded answer, even
    # though MCP connected fine.
    async def fake_create_subprocess_exec(*args, **kwargs):
        leaked = '<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name="plane-workspace">'
        stdout = _ndjson(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": leaked}]},
            },
            # Claude Code's own final "result" event mirrors the last
            # assistant text as `result` -- the leaked text ends up there
            # too, which is exactly what makes this dangerous: it isn't
            # just a stray intermediate event, it's the CLI's own notion of
            # "the final answer".
            {"type": "result", "subtype": "success", "is_error": False, "result": leaked},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("list all my projects", timeout_seconds=5)
    assert exc_info.value.code == "AGENT_INVALID_RESPONSE"


async def test_execute_times_out_and_kills_process(monkeypatch, settings):
    proc = FakeProcess(hang=True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("hi", timeout_seconds=0.05)
    assert exc_info.value.code == "AGENT_TIMEOUT"
    assert proc.killed is True


async def test_execute_maps_error_result_to_agent_unavailable(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {"type": "result", "subtype": "error_during_execution", "is_error": True},
        )
        return FakeProcess(stdout=stdout, returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = ClaudeAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("hi", timeout_seconds=5)
    assert exc_info.value.code == "AGENT_UNAVAILABLE"
