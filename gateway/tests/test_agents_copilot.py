import asyncio
import json

import pytest

from app.agents.base import AgentError
from app.agents.copilot import CopilotAgent
from tests.conftest import make_settings


class FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, hang: bool = False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._hang = hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(999)
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


def _ndjson(*events) -> bytes:
    return ("\n".join(json.dumps(e) for e in events)).encode()


@pytest.fixture
def settings():
    return make_settings(agent_cli="copilot", llm_provider="deepseek")


async def test_execute_builds_expected_command(monkeypatch, settings):
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        stdout = _ndjson(
            {"type": "assistant.message", "data": {"content": "You have 3 projects."}},
            {"type": "result", "exitCode": 0},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    result = await agent.execute("list my projects", timeout_seconds=5)

    assert result.answer == "You have 3 projects."
    assert result.cli == "copilot"
    assert result.model == settings.llm_model

    args = captured["args"]
    assert args[0] == "copilot"
    assert "-p" in args and "list my projects" in args
    assert "--available-tools" in args and "plane" in args
    assert "--allow-tool" in args
    assert "--additional-mcp-config" in args
    # Ephemeral config path is passed as "@<path>".
    config_arg = args[args.index("--additional-mcp-config") + 1]
    assert config_arg.startswith("@")

    env = captured["env"]
    assert env["COPILOT_PROVIDER_TYPE"] == "anthropic"  # deepseek maps to anthropic
    assert env["COPILOT_PROVIDER_BASE_URL"] == settings.llm_base_url
    assert env["COPILOT_MODEL"] == settings.llm_model


async def test_execute_times_out_and_kills_process(monkeypatch, settings):
    proc = FakeProcess(hang=True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("hi", timeout_seconds=0.05)

    assert exc_info.value.code == "AGENT_TIMEOUT"
    assert proc.killed is True


async def test_execute_raises_agent_unavailable_when_binary_missing(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError("copilot not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("hi", timeout_seconds=5)
    assert exc_info.value.code == "AGENT_UNAVAILABLE"


async def test_execute_classifies_llm_auth_failure(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {
                "type": "session.error",
                "data": {"message": "401 unauthorized: invalid api key"},
            },
            {"type": "result", "exitCode": 1},
        )
        return FakeProcess(stdout=stdout, returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("hi", timeout_seconds=5)
    assert exc_info.value.code == "LLM_AUTHENTICATION_ERROR"


async def test_execute_extracts_tool_calls_for_audit(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {"type": "tool.call", "data": {"name": "plane.list_projects"}},
            {"type": "assistant.message", "data": {"content": "Done."}},
            {"type": "result", "exitCode": 0},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    result = await agent.execute("hi", timeout_seconds=5)
    assert "plane.list_projects" in result.tools_used


async def test_execute_extracts_reasoning_separately_from_answer(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {
                "type": "assistant.message",
                "data": {
                    "content": "You have 3 projects.",
                    "reasoningText": "The user wants a project list. I'll call list_projects.",
                },
            },
            {"type": "result", "exitCode": 0},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    result = await agent.execute("list my projects", timeout_seconds=5)

    assert result.answer == "You have 3 projects."
    assert result.reasoning == "The user wants a project list. I'll call list_projects."


async def test_execute_reasoning_is_none_when_absent(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {"type": "assistant.message", "data": {"content": "Hello."}},
            {"type": "result", "exitCode": 0},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    result = await agent.execute("hi", timeout_seconds=5)
    assert result.reasoning is None


async def test_execute_raises_mcp_unavailable_on_needs_auth_even_with_answer_text(
    monkeypatch, settings
):
    # Regression test: a real broken deployment had plane-mcp stuck at MCP
    # status "needs-auth" (wrong auth header format). The model still
    # produced *some* text -- it hallucinated a fake tool call once it
    # realized it had no real Plane tools -- which must never be trusted or
    # shown as if it were a grounded answer (root README: "never invent
    # Plane state").
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {
                "type": "session.mcp_server_status_changed",
                "data": {"serverName": "plane", "status": "needs-auth"},
            },
            {
                "type": "assistant.message",
                "data": {"content": "<|DSML|> calls ... ls -la /app"},
            },
            {"type": "result", "exitCode": 0},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("list my projects", timeout_seconds=5)
    assert exc_info.value.code == "MCP_UNAVAILABLE"


async def test_execute_raises_invalid_response_on_leaked_tool_syntax_after_real_tool_use(
    monkeypatch, settings
):
    # Regression test for a real production failure: MCP connects fine and
    # the model makes a genuine first round of tool calls (real
    # `toolRequests` / `tool.execution_complete` events, no MCP status
    # error at all), but a follow-up turn -- after it has the tool results
    # back -- still degrades into emitting fake DSML-style tool-call markup
    # as its "final answer" instead of a real answer. This must never reach
    # the user as if it were grounded in real Plane data.
    async def fake_create_subprocess_exec(*args, **kwargs):
        stdout = _ndjson(
            {
                "type": "assistant.message",
                "data": {"toolRequests": [{"mcpServerName": "plane", "mcpToolName": "project"}]},
            },
            {"type": "tool.execution_start", "data": {"name": "plane-project"}},
            {"type": "tool.execution_complete", "data": {"name": "plane-project"}},
            {
                "type": "assistant.message",
                "data": {
                    "content": (
                        "The project query returned nothing. Let me verify the workspace "
                        "context before concluding.\n\n<｜｜DSML｜｜ calls>\n"
                        '<｜｜DSML｜｜ invoke name="plane-workspace">\n'
                        '<｜｜DSML｜｜ parameter name="action" string="true">list'
                        "</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>"
                    )
                },
            },
            {"type": "result", "exitCode": 0},
        )
        return FakeProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    with pytest.raises(AgentError) as exc_info:
        await agent.execute("list all my projects", timeout_seconds=5)
    assert exc_info.value.code == "AGENT_INVALID_RESPONSE"


async def test_check_available_reports_version(monkeypatch, settings):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(stdout=b"1.0.83\n", returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    agent = CopilotAgent(settings)
    ok, version = await agent.check_available()
    assert ok is True
    assert "1.0.83" in version
