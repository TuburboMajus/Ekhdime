#!/usr/bin/env bash
# Reports the health of every layer of the stack, reusing the gateway's own
# GET /api/v1/health/details (which already aggregates Plane/MCP/STT/TTS/
# agent-CLI status -- see gateway/app/api/health.py) rather than
# duplicating that logic here.
#
# Note on scope: this checks that the configured agent CLI *binary* runs
# (`copilot --version` / `claude --version`), not that your LLM credentials
# are valid -- verifying DeepSeek auth for real means actually running a
# prompt through it, which costs money/time and isn't something a passive
# health check should do automatically. Use `make ask QUERY="..."` for that.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

GATEWAY_PORT="${GATEWAY_PORT:-8088}"
BASE_URL="http://localhost:${GATEWAY_PORT}"
PASS=0
FAIL=0

check() {
  local name="$1" ok="$2" detail="${3:-}"
  if [ "$ok" = "true" ]; then
    printf '[OK] %s\n' "$name"
    PASS=$((PASS + 1))
  else
    printf '[FAIL] %s%s\n' "$name" "${detail:+ - $detail}"
    FAIL=$((FAIL + 1))
  fi
}

if docker info >/dev/null 2>&1; then check "Docker" true; else
  check "Docker" false "daemon unreachable"
  echo; echo "$PASS passed, $FAIL failed"; exit 1
fi

if ! curl -sf "$BASE_URL/api/v1/health" >/dev/null 2>&1; then
  check "Gateway" false "cannot reach $BASE_URL/api/v1/health -- is 'make up' running?"
  echo; echo "$PASS passed, $FAIL failed"
  exit 1
fi
check "Gateway" true

if [ -z "${GATEWAY_API_TOKEN:-}" ]; then
  check "Gateway auth token" false "GATEWAY_API_TOKEN is empty in .env"
  echo; echo "$PASS passed, $FAIL failed"
  exit 1
fi

DETAILS=$(curl -sf -H "Authorization: Bearer $GATEWAY_API_TOKEN" "$BASE_URL/api/v1/health/details") || {
  check "Gateway authenticated health" false "request failed -- check GATEWAY_API_TOKEN"
  echo; echo "$PASS passed, $FAIL failed"
  exit 1
}

field() {
  python3 -c "import json,sys; d=json.loads(sys.argv[1]); cur=d
for k in sys.argv[2:]:
    cur = cur[k]
print(cur)" "$DETAILS" "$@" 2>/dev/null
}

[ "$(field plane)" = "ok" ] \
  && check "Plane" true \
  || check "Plane" false "not reachable, or workspace not bootstrapped yet (see plane/README.md)"

[ "$(field plane_mcp)" = "ok" ] \
  && check "Plane MCP" true \
  || check "Plane MCP" false "MCP server unreachable"

[ "$(field stt)" = "ok" ] \
  && check "Whisper (STT)" true \
  || check "Whisper (STT)" false "speech-stt unreachable"

[ "$(field tts)" = "ok" ] \
  && check "Kokoro (TTS)" true \
  || check "Kokoro (TTS)" false "speech-tts unreachable"

AGENT_TYPE=$(field agent_cli type)
if [ "$(field agent_cli status)" = "ok" ]; then
  check "Agent CLI ($AGENT_TYPE)" true
else
  check "Agent CLI ($AGENT_TYPE)" false "CLI binary not available inside the gateway container"
fi

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
