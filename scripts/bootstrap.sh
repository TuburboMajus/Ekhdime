#!/usr/bin/env bash
# One-time (but safe-to-rerun) setup: verifies prerequisites, creates .env
# from .env.example without clobbering an existing one, generates a random
# gateway token, initializes the plane-mcp git submodule, and explains the
# Plane Phase 1 bootstrap. See ../README.md "Installation".
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1"; exit 1; }

bold "1/6 Checking Docker"
command -v docker >/dev/null 2>&1 || fail "Docker is not installed. See https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || fail "Docker is installed but the daemon isn't reachable (is it running?)."
ok "Docker is installed and reachable"

bold "2/6 Checking Docker Compose"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 plugin not found ('docker compose version' failed)."
ok "Docker Compose v2 available: $(docker compose version --short)"

bold "3/6 Preparing .env"
if [ -f .env ]; then
  ok ".env already exists -- leaving it untouched"
else
  cp .env.example .env
  ok "Created .env from .env.example"

  if command -v openssl >/dev/null 2>&1; then
    TOKEN=$(openssl rand -hex 32)
    # Portable in-place edit (works on both GNU and BSD/macOS sed).
    sed -i.bak "s/^GATEWAY_API_TOKEN=.*/GATEWAY_API_TOKEN=${TOKEN}/" .env && rm -f .env.bak
    ok "Generated a random GATEWAY_API_TOKEN"
  else
    warn "openssl not found -- leaving GATEWAY_API_TOKEN as the .env.example default. Set a strong random value yourself before any non-local use."
  fi
fi

bold "4/6 Checking required directories"
mkdir -p data
ok "data/ present (gateway SQLite DB and TTS cache live in named Docker volumes, not here -- this directory is only a placeholder for anything you choose to bind-mount)"

bold "5/6 Initializing vendored submodules"
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  git submodule update --init --recursive plane-mcp/vendor/plane-mcp-server
  ok "plane-mcp/vendor/plane-mcp-server ready"
else
  warn "Not a git checkout (or git missing) -- skipping submodule init. Make sure plane-mcp/vendor/plane-mcp-server has real source in it before 'make up' (see plane-mcp/README.md)."
fi

bold "6/6 Plane bootstrap status"
# shellcheck disable=SC1091
PLANE_WORKSPACE_SLUG=$(grep -E '^PLANE_WORKSPACE_SLUG=' .env | cut -d= -f2- || true)
PLANE_API_KEY=$(grep -E '^PLANE_API_KEY=' .env | cut -d= -f2- || true)
if [ -z "$PLANE_WORKSPACE_SLUG" ] || [ -z "$PLANE_API_KEY" ]; then
  warn "PLANE_WORKSPACE_SLUG / PLANE_API_KEY are not set yet."
  cat <<'EOF'

  This is expected on a fresh checkout -- Plane needs a workspace and API
  key created through its own UI before anything else in this stack can
  authenticate against it (see plane/README.md "Two-phase bootstrap").

  Next steps:
    1. make plane-up
    2. Open http://localhost:8080, create an account and a workspace
    3. Workspace Settings -> API tokens -> create a token
    4. Put the workspace slug and token into .env
       (PLANE_WORKSPACE_SLUG=..., PLANE_API_KEY=...)
    5. make up

EOF
else
  ok "PLANE_WORKSPACE_SLUG and PLANE_API_KEY are set -- 'make up' should bring up the full stack"
fi

bold "Bootstrap complete."
