"""Claude Code CLI adapter.

Flags verified by actually running `@anthropic-ai/claude-code` 2.1.270
locally against a fake provider (see the root README's "Claude Code" research
notes for the transcripts). Notably:

* `--tools ""` disables every built-in tool (Bash, Edit, WebFetch, ...);
  combined with `--strict-mcp-config` (only load the MCP server we pass on
  the command line) and `--allowedTools "mcp__plane__*"` (auto-approve only
  that server's tools), the model can only ever call Plane MCP tools -- no
  `--dangerously-skip-permissions` needed, which would have been broader
  than necessary.
* `--permission-prompts none` makes any would-be permission prompt an
  automatic denial instead of hanging forever waiting for a TTY that will
  never answer (there is no host/tool wired up to answer prompts here).
* `--output-format stream-json --include-partial-messages --verbose` gives a
  newline-delimited event stream (`system`/`assistant`/`result` events) that
  exposes `tool_use` blocks -- this is what makes tool-call auditability
  (root README section 34) possible; plain `--output-format json` would only
  give the final answer with no tool-call trail.
* A misbehaving/unreachable provider is retried by the CLI itself with
  exponential backoff (observed climbing well past our own timeout), so the
  gateway's own `asyncio.wait_for` + `proc.kill()` is what actually bounds
  request latency -- the CLI will not do it for us.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from app.agents.base import AgentCLI, AgentError, AgentResult
from app.agents.sanitize import looks_like_leaked_tool_syntax
from app.config import Settings
from app.plane.mcp import claude_mcp_config, ephemeral_mcp_config_file

logger = logging.getLogger(__name__)


class ClaudeAgent(AgentCLI):
    name = "claude"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _subprocess_env(self) -> dict[str, str]:
        settings = self.settings
        env = dict(os.environ)
        env["HOME"] = "/home/gateway/.claude-home"
        # Explicit provider config per the root README's DeepSeek section --
        # never rely on credentials already present in the container's
        # environment for a different provider.
        env["ANTHROPIC_BASE_URL"] = settings.llm_base_url
        env["ANTHROPIC_AUTH_TOKEN"] = settings.llm_api_key
        env["ANTHROPIC_MODEL"] = settings.llm_model
        env.pop("ANTHROPIC_API_KEY", None)
        return env

    async def check_available(self) -> tuple[bool, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.settings.claude_bin,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._subprocess_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode != 0:
                return False, stderr.decode("utf-8", "replace").strip()
            return True, stdout.decode("utf-8", "replace").strip()
        except (FileNotFoundError, asyncio.TimeoutError) as exc:
            return False, str(exc)

    async def execute(self, prompt: str, timeout_seconds: int) -> AgentResult:
        settings = self.settings
        config = claude_mcp_config(settings)

        with ephemeral_mcp_config_file(config) as config_path:
            args = [
                settings.claude_bin,
                "-p",
                prompt,
                "--model",
                settings.llm_model,
                "--mcp-config",
                str(config_path),
                "--strict-mcp-config",
                "--allowedTools",
                "mcp__plane__*",
                "--tools",
                "",
                "--permission-prompts",
                "none",
                "--output-format",
                "stream-json",
                "--include-partial-messages",
                "--verbose",
                "--no-session-persistence",
            ]

            start = time.monotonic()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self._subprocess_env(),
                )
            except FileNotFoundError as exc:
                raise AgentError("AGENT_UNAVAILABLE", f"claude CLI not found: {exc}") from exc

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise AgentError(
                    "AGENT_TIMEOUT",
                    f"claude did not complete within {timeout_seconds} seconds",
                )
            except asyncio.CancelledError:
                # The HTTP request was cancelled (client disconnect, or
                # DELETE /api/v1/requests/{id}) -- never leave the CLI
                # subprocess running as an orphan. See root README section 31.
                proc.kill()
                await proc.wait()
                raise

            duration_ms = int((time.monotonic() - start) * 1000)
            answer, reasoning, tools_used, result_event, mcp_error = _parse_events(stdout)

            if mcp_error:
                # As with the Copilot adapter: a model can still emit *some*
                # text even when the Plane MCP server never actually
                # connected/authenticated. That text is never grounded in
                # real Plane data, so per the root README's "never invent
                # Plane state" rule this must surface as an error rather
                # than a false-looking answer, regardless of whether
                # `answer` is non-empty.
                raise AgentError("MCP_UNAVAILABLE", mcp_error)

            if answer and looks_like_leaked_tool_syntax(answer):
                # See app/agents/sanitize.py / copilot.py's matching check:
                # a follow-up turn can leak fake tool-call markup as literal
                # text after a genuinely successful first round of tool
                # calls. Never surface that as if it were a real answer.
                raise AgentError(
                    "AGENT_INVALID_RESPONSE",
                    "The model produced a malformed response instead of a real answer "
                    "(leaked tool-call syntax). This is a known reliability issue with "
                    f"{settings.llm_model!r} on multi-step tool use -- try again, or "
                    "use a more capable model.",
                )

            if not answer:
                message = (
                    (result_event or {}).get("result")
                    or stderr.decode("utf-8", "replace").strip()
                    or "no output"
                )
                raise AgentError(_classify_failure(message, result_event), message)

            return AgentResult(
                answer=answer,
                cli=self.name,
                model=settings.llm_model,
                duration_ms=duration_ms,
                exit_code=proc.returncode or 0,
                tools_used=tools_used,
                metadata={"result": result_event},
                reasoning=reasoning,
            )


def _parse_events(
    stdout: bytes,
) -> tuple[str, str | None, list[str], dict | None, str | None]:
    """Parse Claude Code's `stream-json` event stream.

    Returns (answer, reasoning, tools_used, final_result_event, mcp_error).

    `reasoning` is collected from `thinking`-type content blocks (Claude's
    extended-thinking output), kept separate from `answer` (`text`-type
    blocks) so the API/mobile app can render it as a collapsed-by-default
    "Thinking" section instead of mixing it into the visible response.
    `mcp_error` comes from the `system`/`init` event's `mcp_servers` list --
    per Claude Code's docs, status `failed` or `needs-auth` means that
    server's tools were never actually available for the turn.
    """
    answer = ""
    reasoning_parts: list[str] = []
    tools_used: list[str] = []
    result_event: dict | None = None
    mcp_error: str | None = None

    for line in stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            for server in event.get("mcp_servers", []):
                if server.get("name") == "plane" and server.get("status") in (
                    "failed",
                    "needs-auth",
                ):
                    mcp_error = f"Plane MCP server status: {server.get('status')}"
        elif etype == "assistant":
            content = (event.get("message") or {}).get("content") or []
            for block in content:
                if block.get("type") == "text" and block.get("text"):
                    answer = block["text"]
                elif block.get("type") == "thinking" and block.get("thinking"):
                    reasoning_parts.append(block["thinking"])
                elif block.get("type") == "tool_use":
                    name = block.get("name", "")
                    if name.startswith("mcp__"):
                        tools_used.append(name)
        elif etype == "result":
            result_event = event
            if not event.get("is_error") and event.get("result"):
                answer = event["result"]

    reasoning = "\n\n".join(reasoning_parts) if reasoning_parts else None
    return answer, reasoning, tools_used, result_event, mcp_error


def _classify_failure(message: str, result_event: dict | None) -> str:
    subtype = (result_event or {}).get("subtype", "")
    lowered = f"{message} {subtype}".lower()
    if "mcp" in lowered:
        return "MCP_UNAVAILABLE"
    if any(term in lowered for term in ("401", "unauthorized", "authentication")):
        return "LLM_AUTHENTICATION_ERROR"
    if any(term in lowered for term in ("429", "rate limit", "overloaded")):
        return "LLM_RATE_LIMITED"
    return "AGENT_UNAVAILABLE"
