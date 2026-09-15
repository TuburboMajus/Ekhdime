"""Locks in the MCP auth header format -- this had no test coverage before
and was wrong in production: the gateway sent `x-api-key` as a custom
header, but plane-mcp's `PlaneHeaderAuthProvider` extends FastMCP's
`TokenVerifier`, which requires the credential as a standard
`Authorization: Bearer <token>` header. Every MCP connection silently sat
at status "needs-auth" as a result, so the agent never saw any real Plane
tools -- confirmed live: `x-api-key` alone got `401 invalid_token` from a
running plane-mcp container, `Authorization: Bearer <key>` got a real `200`
`initialize` response. See app/plane/mcp.py's module docstring.
"""

from app.plane.mcp import claude_mcp_config, copilot_mcp_config
from tests.conftest import make_settings


def _settings():
    return make_settings(
        plane_api_key="plane_api_abc123", plane_workspace_slug="my-workspace"
    )


def test_copilot_mcp_config_sends_bearer_authorization_header():
    config = copilot_mcp_config(_settings())
    headers = config["mcpServers"]["plane"]["headers"]
    assert headers["Authorization"] == "Bearer plane_api_abc123"
    assert headers["x-workspace-slug"] == "my-workspace"
    assert "x-api-key" not in headers


def test_claude_mcp_config_sends_bearer_authorization_header():
    config = claude_mcp_config(_settings())
    headers = config["mcpServers"]["plane"]["headers"]
    assert headers["Authorization"] == "Bearer plane_api_abc123"
    assert headers["x-workspace-slug"] == "my-workspace"
    assert "x-api-key" not in headers


def test_copilot_mcp_config_shape():
    config = copilot_mcp_config(_settings())
    server = config["mcpServers"]["plane"]
    assert server["type"] == "http"
    assert server["url"] == _settings().plane_mcp_url
    assert server["tools"] == ["*"]


def test_claude_mcp_config_shape():
    config = claude_mcp_config(_settings())
    server = config["mcpServers"]["plane"]
    assert server["type"] == "http"
    assert server["url"] == _settings().plane_mcp_url
    # Claude's config format has no "tools" field (unlike Copilot's).
    assert "tools" not in server
