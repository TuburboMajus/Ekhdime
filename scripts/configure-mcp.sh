#!/usr/bin/env bash
# Registers the running Plane MCP server with your OWN local Copilot/Claude
# CLI installation, for interactive debugging outside the gateway (the
# gateway itself never uses this -- it generates an ephemeral MCP config
# per request; see gateway/app/plane/mcp.py).
#
# This is useful for manually poking at the Plane MCP tools from your own
# terminal, e.g.:
#   copilot --available-tools plane --allow-tool plane -p "list my projects"
#
# Requires PLANE_MCP_EXPOSE_PORT=true in .env (see plane-mcp/README.md) and
# either the `copilot` or `claude` CLI (or both) installed locally.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f .env ]; then
  echo ".env not found -- run ./scripts/bootstrap.sh first." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

: "${PLANE_MCP_HOST_PORT:=8100}"
: "${PLANE_API_KEY:?PLANE_API_KEY is not set in .env -- complete the Plane Phase 1 bootstrap first (see plane/README.md)}"
: "${PLANE_WORKSPACE_SLUG:?PLANE_WORKSPACE_SLUG is not set in .env -- complete the Plane Phase 1 bootstrap first (see plane/README.md)}"

MCP_URL="http://localhost:${PLANE_MCP_HOST_PORT}/http/api-key/mcp"

# Any HTTP response (even 4xx/405) proves the port is up and speaking HTTP;
# only a connection failure means it's actually unreachable.
if ! curl -s -o /dev/null -w '%{http_code}' "$MCP_URL" | grep -qE '^[0-9]{3}$'; then
  echo "Could not reach $MCP_URL -- is PLANE_MCP_EXPOSE_PORT=true in .env, and is the stack up ('make up')?" >&2
  exit 1
fi

REGISTERED_ANY=false

if command -v copilot >/dev/null 2>&1; then
  copilot mcp remove plane >/dev/null 2>&1 || true
  copilot mcp add --transport http \
    --header "x-api-key: ${PLANE_API_KEY}" \
    --header "x-workspace-slug: ${PLANE_WORKSPACE_SLUG}" \
    plane "$MCP_URL"
  echo "[OK] Registered 'plane' MCP server with your local Copilot CLI (~/.copilot/mcp-config.json)."
  echo "     Try: copilot --available-tools plane --allow-tool plane -p \"list my projects\""
  REGISTERED_ANY=true
else
  echo "[SKIP] 'copilot' not found on PATH."
fi

if command -v claude >/dev/null 2>&1; then
  claude mcp remove plane >/dev/null 2>&1 || true
  # Unlike `copilot mcp add`, Claude's CLI requires --header to come AFTER
  # the positional name/url args -- verified live (the reverse order fails
  # with "error: missing required argument 'name'").
  claude mcp add --transport http plane "$MCP_URL" \
    --header "x-api-key: ${PLANE_API_KEY}" \
    --header "x-workspace-slug: ${PLANE_WORKSPACE_SLUG}"
  echo "[OK] Registered 'plane' MCP server with your local Claude Code CLI."
  echo "     Try: claude -p \"list my projects\" --allowedTools 'mcp__plane__*' --tools \"\""
  REGISTERED_ANY=true
else
  echo "[SKIP] 'claude' not found on PATH."
fi

if [ "$REGISTERED_ANY" = false ]; then
  echo "Neither 'copilot' nor 'claude' is installed locally -- nothing to configure." >&2
  echo "(They're installed inside the gateway container regardless -- this script is only for local, interactive debugging.)" >&2
  exit 1
fi
