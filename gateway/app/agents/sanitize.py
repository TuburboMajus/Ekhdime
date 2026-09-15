"""Detects a model completion that leaked raw pseudo-tool-call markup
instead of either calling a real tool or answering in plain text.

Observed live with `deepseek-v4-flash` via Copilot CLI's Anthropic-compatible
bridge: a *first* round of tool calls can succeed completely normally
(visible in Copilot's own session log as real `toolRequests` /
`tool.execution_complete` events), and a *follow-up* turn -- after the model
has the tool results back -- still sometimes degrades into emitting a fake
`<｜｜DSML｜｜ calls>...` block as literal text instead of either calling a
real tool again or giving a plain-text answer. This is not something Copilot
recognizes as a tool call (confirmed: no `tool.execution_*` event follows
it, and plane-mcp never receives a request) -- it never executes anything --
but it must never be shown to a user as if it were a real, grounded answer
either. Root README section 72 ("never invent Plane state") applies just as
much to "the model produced garbage" as it does to "MCP was unreachable".
"""

from __future__ import annotations

# The exact marker this failure mode leaks: a fullwidth vertical bar
# (U+FF5C), doubled, wrapping a token name -- almost certainly DeepSeek's
# own internal tool-call delimiter leaking through unformatted when the
# provider bridge doesn't translate it. Vanishingly unlikely to appear in a
# legitimate answer about a Plane workspace, so a plain substring check is
# enough; no need for a fuzzy/ML-based classifier here.
_LEAK_MARKERS = ("｜｜DSML｜｜", "｜｜calls>", "｜｜invoke")


def looks_like_leaked_tool_syntax(text: str) -> bool:
    if not text:
        return False
    return any(marker in text for marker in _LEAK_MARKERS)
