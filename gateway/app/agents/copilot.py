"""GitHub Copilot CLI adapter.

Every flag below was verified by actually running `@github/copilot` 1.0.83
locally (`copilot --help`, `copilot help providers`, `copilot help
permissions`, and live invocations against a fake provider) rather than
assumed from documentation -- see the research notes in the root README's
"Copilot CLI" section for the transcripts. In particular:

* `--available-tools plane` is what actually strips out every built-in tool
  (shell, write, edit, web-fetch, ...) so the model can ONLY see the Plane
  MCP tools -- confirmed via the CLI's own
  `session.info: "Disabled tools: bash, create, edit, ..."` log line.
* `--output-format json` is NOT a single JSON object; it is newline-delimited
  JSON events (session/model/assistant/result events), ending in one
  `{"type": "result", ...}` line. `_parse_events` below handles that.
* BYOK (DeepSeek via its Anthropic-compatible endpoint) is activated purely
  by environment variables (`COPILOT_PROVIDER_*`); no GitHub login is used
  or required.
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
from app.plane.mcp import copilot_mcp_config, ephemeral_mcp_config_file

logger = logging.getLogger(__name__)

# DeepSeek's OpenAI-*and*-Anthropic-compatible endpoints both exist; the root
# README standardizes on the Anthropic-compatible one for Copilot. Other
# providers fall back to Copilot's own default ("openai"), which also covers
# any other OpenAI-compatible backend a deployer might point LLM_BASE_URL at.
_PROVIDER_TYPE_BY_LLM_PROVIDER = {
    "deepseek": "anthropic",
    "anthropic": "anthropic",
}


class CopilotAgent(AgentCLI):
    name = "copilot"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _provider_env(self) -> dict[str, str]:
        settings = self.settings
        provider_type = _PROVIDER_TYPE_BY_LLM_PROVIDER.get(settings.llm_provider.lower(), "openai")
        env = {
            "COPILOT_PROVIDER_BASE_URL": settings.llm_base_url,
            "COPILOT_PROVIDER_TYPE": provider_type,
            "COPILOT_PROVIDER_API_KEY": settings.llm_api_key,
            "COPILOT_MODEL": settings.llm_model,
        }
        return env

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # A private, ephemeral home directory keeps ~/.copilot state (auth
        # cache, session logs) out of the way of concurrent requests and
        # off any host bind mount -- see the root README's "no sensitive
        # host filesystem in the agent's working directory" rule.
        env["HOME"] = "/home/gateway/.copilot-home"
        env["COPILOT_ALLOW_ALL"] = "false"
        env.update(self._provider_env())
        return env

    async def check_available(self) -> tuple[bool, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.settings.copilot_bin,
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
        config = copilot_mcp_config(settings)

        with ephemeral_mcp_config_file(config) as config_path:
            args = [
                settings.copilot_bin,
                "-p",
                prompt,
                "--model",
                settings.llm_model,
                "--additional-mcp-config",
                f"@{config_path}",
                "--available-tools",
                "plane",
                "--allow-tool",
                "plane",
                "--no-color",
                "--output-format",
                "json",
            ]

            start = time.monotonic()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self._subprocess_env(),
                )
            except FileNotFoundError as exc:
                raise AgentError("AGENT_UNAVAILABLE", f"copilot CLI not found: {exc}") from exc

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise AgentError(
                    "AGENT_TIMEOUT",
                    f"copilot did not complete within {timeout_seconds} seconds",
                )
            except asyncio.CancelledError:
                # The HTTP request was cancelled (client disconnect, or
                # DELETE /api/v1/requests/{id}) -- never leave the CLI
                # subprocess running as an orphan. See root README section 31.
                proc.kill()
                await proc.wait()
                raise

            duration_ms = int((time.monotonic() - start) * 1000)
            answer, reasoning, tools_used, result_meta, session_error = _parse_events(stdout)

            if session_error and "mcp" in session_error.lower():
                # A model can still emit *some* text even when the Plane MCP
                # server never actually authenticated (it did here: it
                # hallucinated a fake tool call once it realized it had no
                # real tools). That text is never grounded in real Plane
                # data, so per the root README's "never invent Plane state"
                # rule this must surface as an error, not a false-looking
                # answer, regardless of whether `answer` is non-empty.
                raise AgentError("MCP_UNAVAILABLE", session_error)

            if answer and looks_like_leaked_tool_syntax(answer):
                # Observed live: a first round of *real* tool calls can
                # succeed completely normally, and a follow-up turn --
                # after the model has the tool results back -- still
                # degrades into emitting fake tool-call markup as literal
                # text instead of a real answer (see app/agents/sanitize.py
                # for the full incident notes). That text was never a real
                # answer and must not reach the user as one.
                raise AgentError(
                    "AGENT_INVALID_RESPONSE",
                    "The model produced a malformed response instead of a real answer "
                    "(leaked tool-call syntax). This is a known reliability issue with "
                    f"{settings.llm_model!r} on multi-step tool use -- try again, or "
                    "use a more capable model.",
                )

            if not answer:
                message = session_error or stderr.decode("utf-8", "replace").strip() or "no output"
                raise AgentError(_classify_failure(message), message)

            return AgentResult(
                answer=answer,
                cli=self.name,
                model=settings.llm_model,
                duration_ms=duration_ms,
                exit_code=proc.returncode or 0,
                tools_used=tools_used,
                metadata={"result": result_meta},
                reasoning=reasoning,
            )


def _parse_events(stdout: bytes) -> tuple[str, str | None, list[str], dict, str | None]:
    """Parse copilot's NDJSON `--output-format json` event stream.

    Returns (answer, reasoning, tools_used, final_result_event,
    session_error_message).

    `reasoning` comes from `assistant.message.data.reasoningText` (a flat
    string) -- confirmed live: a real `assistant.message` event carries both
    `content` (the final answer) and a separate `reasoningText` /
    `reasoningBlocks.blocks[].thinking` (the model's chain-of-thought for
    that turn). Kept out of `answer` so the API/mobile app can render it as
    a collapsed-by-default "Thinking" section instead of mixing it into the
    visible response.
    """
    answer = ""
    reasoning: str | None = None
    tools_used: list[str] = []
    result_meta: dict = {}
    session_error: str | None = None

    for line in stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = event.get("type", "")
        data = event.get("data", {}) or {}

        if etype == "assistant.message":
            content = data.get("content")
            if isinstance(content, str) and content.strip():
                answer = content
            text = data.get("reasoningText")
            if isinstance(text, str) and text.strip():
                reasoning = text
        elif etype == "session.mcp_server_status_changed" and data.get("status") in (
            "failed",
            "needs-auth",
        ):
            # "needs-auth" means the MCP connection never actually
            # authenticated (e.g. a wrong header format/credential) -- the
            # model then has no real Plane tools for the whole turn, which
            # is exactly as broken as a hard connection failure even though
            # Copilot doesn't call it "failed". Missing this classification
            # is what let a real misconfiguration silently produce a
            # hallucinated answer instead of a clear MCP_UNAVAILABLE error.
            detail = data.get("error") or f"MCP server status: {data.get('status')}"
            session_error = detail
        elif etype == "session.error":
            session_error = data.get("message") or session_error
        elif etype == "result":
            result_meta = event
        elif "tool" in etype:
            name = data.get("name") or data.get("tool")
            if name:
                tools_used.append(name)

    return answer, reasoning, tools_used, result_meta, session_error


def _classify_failure(message: str) -> str:
    lowered = message.lower()
    if "mcp" in lowered:
        return "MCP_UNAVAILABLE"
    if any(term in lowered for term in ("401", "unauthorized", "authentication")):
        return "LLM_AUTHENTICATION_ERROR"
    if any(term in lowered for term in ("429", "rate limit")):
        return "LLM_RATE_LIMITED"
    return "AGENT_UNAVAILABLE"
