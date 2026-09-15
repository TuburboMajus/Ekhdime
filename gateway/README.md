# Gateway

The FastAPI service that ties everything together: it owns conversation
history, builds prompts, shells out to an agent CLI (Copilot or Claude),
and orchestrates Whisper (STT) and Kokoro (TTS). This is the **only**
component the mobile app (or `scripts/ask-plane.sh`) ever talks to -- see
the root README's design principles and [`API.md`](API.md) for the full,
authoritative API contract.

Verified, end to end, by actually building and running this image (not just
unit tests): the container builds, both CLIs (`copilot --version` / `claude
--version`) work inside it, the health check passes, and real `curl` calls
against a running container return the documented response shapes for
`/health`, `/info`, `/health/details`, `/query` (correctly refusing with
`PLANE_UNAVAILABLE` before Phase 1 bootstrap), and `/conversations`.

## Architecture

```text
app/
├── main.py            FastAPI app factory, startup safety checks, request-id middleware
├── config.py           Settings (env-driven; see .env.example)
├── logging_config.py    structured JSON logging, secret redaction
├── api/                 routers: health, query, audio, sessions, shared errors/deps
├── agents/                AgentCLI interface + CopilotAgent/ClaudeAgent + factory
├── plane/                  ephemeral MCP config generation + infra-only health checks
├── speech/                  Whisper client, Kokoro client, bounded TTS cache, ffprobe duration check
├── prompts/                  Jinja2 renderer for ../prompts/plane-assistant.md
├── sessions/                   SQLAlchemy models + repository (Conversation/Message)
└── security/                    bearer-token auth dependency
```

## Design rules this code follows (and how)

* **Plane only through MCP** (root README 2.2) -- `app/plane/health.py` is
  the *only* file that calls Plane's REST API directly, and only for a
  liveness probe. All business logic reaches Plane exclusively via the MCP
  tools the agent CLI calls.
* **No hard-coded LLM/CLI** (2.3, 2.4) -- `AgentCLI` (`agents/base.py`) is
  the sole interface `api/query.py` depends on; `agents/factory.py` is the
  only place that branches on `AGENT_CLI`. Swapping `LLM_MODEL` never
  touches source.
* **No shell injection** (13) -- every subprocess call uses
  `asyncio.create_subprocess_exec` with an argument list; nothing is ever
  interpolated into a shell string.
* **Restricted agent capabilities** (14) -- Copilot is invoked with
  `--available-tools plane` (verified live: this disables every built-in
  tool -- bash, write, edit, web-fetch -- leaving only the Plane MCP tools
  visible to the model); Claude is invoked with `--tools ""
  --strict-mcp-config --allowedTools mcp__plane__*`. The container runs as
  a non-root user with no Docker socket, no host filesystem mount.
* **CLI output normalization** (32) -- `agents/copilot.py` parses Copilot's
  NDJSON `--output-format json` event stream; `agents/claude.py` parses
  Claude's `stream-json` event stream. Both return the same `AgentResult`.
* **Structured logs, no secrets** (33) -- `logging_config.py` redacts any
  field named like a token/key/authorization header before it's ever
  serialized.
* **Correctness over guessing** (72) -- every failure mode (MCP down, LLM
  auth failure, timeout, malformed CLI output) maps to a specific error code
  in `api/errors.py`; nothing falls back to inventing an answer.

## Configuration

See [`.env.example`](.env.example) -- every variable there maps 1:1 to a
field in `app/config.py:Settings`. The most important ones to actually
change before running for real:

| Variable | Why |
| --- | --- |
| `GATEWAY_API_TOKEN` | The gateway refuses to start with the default in `ENVIRONMENT=production` |
| `AGENT_CLI` | `copilot` or `claude` |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | Your DeepSeek (or other) credentials |
| `PLANE_WORKSPACE_SLUG` / `PLANE_API_KEY` | Filled in after Plane's Phase 1 bootstrap (see `../plane/README.md`) |

## Running standalone

Requires a reachable Plane MCP server (and, for full functionality,
speech-stt/speech-tts) on the `plane-assistant` Docker network -- see the
root README for the full-stack path. To just build and boot the gateway in
isolation (e.g. to poke at `/docs`):

```bash
cd gateway
cp .env.example .env   # at minimum set GATEWAY_API_TOKEN
docker compose up -d --build
curl http://localhost:8088/api/v1/health
```

## Tests

```bash
cd gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                 # 72 tests: config, prompt building, auth, both agent
                        # adapters (command construction, timeout+kill,
                        # output parsing, failure classification), session
                        # storage, STT/TTS clients, TTS cache, and full
                        # API-level integration tests via FastAPI's TestClient
ruff check app tests
```

Two real bugs were caught this way and are now covered by regression tests:
a FastAPI dependency (`get_agent_semaphore`) that silently turned every
`POST` route into a broken multi-body-parameter endpoint (`tests/test_api_query.py`),
and a `MissingGreenlet` crash from accessing a lazy-loaded SQLAlchemy
relationship outside its async context (`tests/test_sessions.py::test_get_with_messages_eager_loads`).

## API

See [`API.md`](API.md) for the complete, authoritative endpoint reference
(request/response shapes, error codes) -- this is what the mobile app and
`scripts/ask-plane.sh` are both written against. In development,
`GET /docs` also serves live Swagger UI.

## Curl examples

```bash
TOKEN=your-gateway-token

curl http://localhost:8088/api/v1/health

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8088/api/v1/health/details

curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "list all my projects"}' \
  http://localhost:8088/api/v1/query

curl -H "Authorization: Bearer $TOKEN" \
  -F "file=@recording.m4a" -F "include_audio=true" \
  http://localhost:8088/api/v1/query/audio

curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test."}' \
  http://localhost:8088/api/v1/tts --output speech.mp3
```
