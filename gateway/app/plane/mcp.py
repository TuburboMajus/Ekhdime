"""Builds ephemeral, per-invocation MCP client configuration for the agent CLIs.

Design rule 2.2 (root README): normal user queries must reach Plane only
through MCP, never through a hand-rolled REST call in this codebase. This
module is what wires each CLI subprocess up to the Plane MCP server.

Credentials (the workspace API key) travel as HTTP headers on the MCP
connection, not as files baked into an image or a long-lived config on disk
-- see plane-mcp/README.md "How authentication actually works". Two
separate hops, easy to conflate (an earlier version of this file did,
which silently broke every MCP connection -- found via a live container
whose MCP status stuck at "needs-auth" and whose model, seeing no real
Plane tools, hallucinated a fake `bash` tool call instead):

* Client (this gateway's spawned CLI) -> plane-mcp: plane-mcp's
  `PlaneHeaderAuthProvider` extends FastMCP's `TokenVerifier`, which
  extracts the credential from a standard **`Authorization: Bearer
  <token>`** header (confirmed: `TokenVerifier.verify_token`'s docstring is
  literally "Verify a bearer token", and a live curl test sending
  `x-api-key` alone got `401 invalid_token`, while `Authorization: Bearer`
  got a real `200` MCP `initialize` response). `x-workspace-slug` is a
  genuinely separate custom header, read directly off the request.
* plane-mcp -> Plane's own REST API: re-packages that same value as
  Plane's native `x-api-key` header (see
  `plane_header_auth_provider.py::_validate_api_key`). This second hop is
  internal to plane-mcp and irrelevant to what this gateway sends.

The config files this module writes are created with `tempfile` (mode 0600,
in a private temp dir) and must be deleted by the caller after the CLI
subprocess exits -- see `agents/copilot.py` / `agents/claude.py`.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.config import Settings

MCP_SERVER_NAME = "plane"


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.plane_api_key}",
        "x-workspace-slug": settings.plane_workspace_slug,
    }


def copilot_mcp_config(settings: Settings) -> dict:
    """Shape verified against a real `copilot mcp add --transport http --json` run."""
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "type": "http",
                "url": settings.plane_mcp_url,
                "tools": ["*"],
                "headers": _headers(settings),
            }
        }
    }


def claude_mcp_config(settings: Settings) -> dict:
    """Shape per Claude Code's documented `.mcp.json` format for an http server."""
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "type": "http",
                "url": settings.plane_mcp_url,
                "headers": _headers(settings),
            }
        }
    }


@contextmanager
def ephemeral_mcp_config_file(config: dict):
    """Write `config` to a private temp file and guarantee cleanup."""
    fd, path_str = tempfile.mkstemp(prefix="plane-mcp-config-", suffix=".json")
    path = Path(path_str)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w") as fh:
            json.dump(config, fh)
        yield path
    finally:
        path.unlink(missing_ok=True)
