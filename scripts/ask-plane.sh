#!/usr/bin/env bash
# Command-line convenience wrapper around the gateway's own
# POST /api/v1/query -- this does NOT duplicate any orchestration logic; it
# is a thin curl call through the exact same HTTP -> CLI -> MCP -> Plane
# path the mobile app uses (see gateway/API.md). See root README section 15.
#
# Usage:
#   ./scripts/ask-plane.sh "list all my projects"
#   ./scripts/ask-plane.sh "what should I work on now?" --conversation-id <uuid>
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

if [ -z "${GATEWAY_API_TOKEN:-}" ] || [ "${GATEWAY_API_TOKEN:-}" = "change-me" ]; then
  echo "GATEWAY_API_TOKEN is not set (or still the unsafe default) in .env." >&2
  exit 1
fi

QUERY="${1:-}"
if [ -z "$QUERY" ]; then
  echo "Usage: $0 \"<question>\" [--conversation-id <uuid>]" >&2
  exit 1
fi
shift || true

CONVERSATION_ID=""
if [ "${1:-}" = "--conversation-id" ]; then
  CONVERSATION_ID="${2:-}"
fi

PAYLOAD=$(python3 -c "
import json, sys
query, conversation_id = sys.argv[1], sys.argv[2] or None
print(json.dumps({'query': query, 'conversation_id': conversation_id, 'include_audio': False}))
" "$QUERY" "$CONVERSATION_ID")

# No -f: a non-2xx response (e.g. 503 PLANE_UNAVAILABLE) still has a JSON
# error envelope in the body that we want to show the user, not just curl's
# generic failure. Only an actual transport-level failure (connection
# refused, timeout) means the gateway is unreachable.
HTTP_CODE=$(curl -s -o /tmp/ask-plane-response.$$ -w '%{http_code}' -X POST "$BASE_URL/api/v1/query" \
  -H "Authorization: Bearer $GATEWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD") || {
  echo "Request to $BASE_URL/api/v1/query failed. Is 'make up' running? Try ./scripts/healthcheck.sh" >&2
  rm -f /tmp/ask-plane-response.$$
  exit 1
}
RESPONSE=$(cat /tmp/ask-plane-response.$$)
rm -f /tmp/ask-plane-response.$$

if [ "$HTTP_CODE" = "000" ]; then
  echo "Request to $BASE_URL/api/v1/query failed (server unreachable). Is 'make up' running? Try ./scripts/healthcheck.sh" >&2
  exit 1
fi

python3 -c "
import json, sys
body = json.loads(sys.argv[1])
if 'error' in body:
    err = body['error']
    print(f\"Error [{err['code']}]: {err['message']}\", file=sys.stderr)
    sys.exit(1)
print(body['answer'])
print(f\"\n(conversation: {body['conversation_id']}, agent: {body['agent']['cli']}/{body['agent']['model']}, {body['duration_ms']}ms)\", file=sys.stderr)
" "$RESPONSE"
