# Plane MCP Voice Assistant

A fully self-hosted project-management assistant built around **Plane
Community Edition** and the **official Plane MCP server**. Ask it things
like "what should I work on now?" or "create a high-priority task called
'fix gateway reconnect' in Infrastructure" -- by voice from an Android app
or by text from a terminal -- and it answers using an AI agent CLI
(GitHub Copilot CLI or Claude Code) that reasons over your real Plane data
through MCP.

```text
Android app  --(HTTPS, bearer token)-->  Gateway (FastAPI)
                                             |        |          |
                                        Whisper   Copilot/Claude  Kokoro
                                          (STT)    CLI -> MCP ->   (TTS)
                                                    Plane
```

Every business-level question or command reaches Plane **only** through the
official Plane MCP server -- never through a hand-rolled REST call baked
into the gateway. See "Design principles" below.

## Repository layout

This repository is decomposed into independently runnable, independently
dockerized components. Each has its own `README.md`, `.env.example`,
`Dockerfile`, and `docker-compose.yml`; this root directory combines them.

```text
.
├── docker-compose.yml         combines every component via `include:`
├── docker-compose.gpu.yml     optional GPU override for the speech services
├── .env.example               single .env for running the full stack
├── Makefile                   bootstrap / plane-up / up / down / test / ask / mobile-*
├── config/versions.env         pinned upstream versions, single source of truth
├── prompts/plane-assistant.md   the system prompt (editable without rebuilding images)
├── scripts/                     bootstrap.sh, healthcheck.sh, ask-plane.sh, configure-mcp.sh
│
├── plane/                 Plane Community Edition (official images, lightly adapted)
├── plane-mcp/              official Plane MCP server (vendored git submodule, built locally)
├── gateway/                  FastAPI orchestrator: agents, prompts, sessions, speech clients
│   └── API.md                   the authoritative REST API contract
├── speech-stt/                Whisper ASR Webservice (faster-whisper)
├── speech-tts/                  Kokoro-FastAPI (OpenAI-compatible TTS)
└── mobile/                       Flutter Android client
```

Read each component's own README for details specific to it; this document
covers the full-stack picture, prerequisites, and end-to-end operation.

## Design principles

1. **Plane is the source of truth.** Nothing here re-implements
   projects/issues/states/priorities -- that all lives in Plane.
2. **AI access to Plane goes through MCP, always** -- with one narrow,
   explicit exception: infra-level health/connectivity checks
   (`gateway/app/plane/health.py`) may call Plane's REST API directly.
   Every *business* question or mutation goes through the agent CLI's MCP
   tool calls.
3. **The gateway invokes a CLI agent** (Copilot or Claude), it does not call
   an LLM API directly from Python. `AGENT_CLI=copilot|claude` selects which,
   and nothing else in the codebase branches on that choice
   (`gateway/app/agents/factory.py` is the only place that does).
4. **The LLM provider is generic configuration**, not hard-coded. The
   initial provider is DeepSeek; changing `LLM_MODEL`/`LLM_BASE_URL` never
   requires a source change.
5. **Never invent Plane state.** If MCP/Plane is unreachable, the system
   says so (`PLANE_UNAVAILABLE`/`MCP_UNAVAILABLE`) rather than guessing.

## Prerequisites

* Docker Engine 24+ and Docker Compose v2 (`docker compose version`)
* ~4GB RAM free for Plane alone, more for the speech services (see
  `speech-stt/README.md` for per-model-size RAM guidance)
* `git` (for the `plane-mcp` submodule)
* A DeepSeek API key (or another Anthropic/OpenAI-compatible provider) --
  see [console.deepseek.com](https://platform.deepseek.com/)
* For the mobile app: the Flutter SDK (only if building/running it yourself
  rather than via the provided Docker build)
* Optional: an NVIDIA GPU + NVIDIA Container Toolkit, for accelerated speech

Nothing else needs to be installed on the host -- Plane, the MCP server, the
gateway (with both agent CLIs baked in), and the speech services all run in
containers.

## Installation and bootstrap

Plane requires a human to create an account and workspace before anything
else can authenticate against it, so startup is a deliberate two-phase
process.

```bash
git clone --recurse-submodules <this-repo-url>
cd plane-assistant   # or whatever you cloned it as
make bootstrap        # creates .env, generates a random GATEWAY_API_TOKEN,
                       # initializes the plane-mcp submodule if you forgot
                       # --recurse-submodules
```

**Phase 1 -- start Plane and create a workspace:**

```bash
make plane-up
```

Open `http://localhost:8080`, create an account, create a workspace, then
go to **Workspace Settings -> API tokens** and create a token. Put both
values into `.env`:

```env
PLANE_WORKSPACE_SLUG=my-workspace
PLANE_API_KEY=plane_api_xxxxxxxxxxxxxxxx
```

Also set your LLM credentials in `.env`:

```env
LLM_API_KEY=your-deepseek-api-key
```

**Phase 2 -- start everything else:**

```bash
make up
```

`make up` refuses to run (with a clear error) if `PLANE_WORKSPACE_SLUG`/
`PLANE_API_KEY` are still blank -- see `Makefile`'s `check-plane-configured`
target -- rather than starting a half-functional gateway.

Verify everything is actually working:

```bash
make health
```

```text
[OK] Docker
[OK] Gateway
[OK] Plane
[OK] Plane MCP
[OK] Whisper (STT)
[OK] Kokoro (TTS)
[OK] Agent CLI (copilot)
```

Then try it:

```bash
make ask QUERY="list all my projects"
```

## Component setup notes

### Plane

Runs the official self-hosted images, pinned to `v1.4.2`, on the shared
`plane-assistant` Docker network. One deliberate deviation from upstream:
`minio/minio` on Docker Hub now rejects anonymous pulls, so this uses the
`quay.io/minio/minio` mirror instead. See `plane/README.md` for the full,
itemized list of changes and the backup/upgrade procedure.

### Plane MCP server

The **official** Python/FastMCP implementation
([makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server)),
vendored as a pinned git submodule and built locally (no prebuilt image is
published upstream). Runs in Streamable-HTTP mode. Authentication is
per-request via `x-api-key`/`x-workspace-slug` headers that the gateway
attaches when it spins up an agent CLI invocation -- verified against the
real server source and confirmed live (a bad key correctly returns `401`
after a real round-trip to Plane). See `plane-mcp/README.md` for the full
write-up, including a startup quirk (unconditional-but-unused OAuth
transport) that isn't documented anywhere upstream.

### DeepSeek (LLM)

Set in `.env`:

```env
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com/anthropic
LLM_API_KEY=your-key
LLM_MODEL=deepseek-v4-pro
```

The gateway translates these generic settings into whatever each CLI
actually needs (`gateway/app/agents/copilot.py` / `claude.py`) -- changing
`LLM_MODEL` to another DeepSeek (or Anthropic-compatible) model needs no
code change, just a gateway restart.

### Copilot CLI (default agent)

Installed inside the gateway image (`@github/copilot`, pinned version in
`config/versions.env`). Every flag the adapter uses was verified by actually
running the CLI (see `gateway/app/agents/copilot.py`'s module docstring):
`--available-tools plane` restricts the model to *only* the Plane MCP
tools (confirmed via the CLI's own "Disabled tools: bash, create, edit, ..."
log line), and BYOK mode is activated purely through
`COPILOT_PROVIDER_*` environment variables -- no GitHub login involved.

### Claude Code (alternative agent)

Installed alongside Copilot in the same image (`@anthropic-ai/claude-code`).
Set `AGENT_CLI=claude` in `.env` to switch. `gateway/app/agents/claude.py`
uses `--tools "" --strict-mcp-config --allowedTools mcp__plane__*` (verified
live) so the model can only ever call Plane MCP tools, with
`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_MODEL` carrying the
same DeepSeek credentials.

Switching between the two requires only editing `.env` and restarting the
gateway (`make restart`) -- both conversation history and the Plane MCP
wiring are identical either way.

## Docker commands

```bash
make plane-up          # Phase 1: Plane only
make up                # Phase 2: everything (requires Plane bootstrap done)
make down               # stop everything
make restart              # down + up
make logs                  # tail every service
make logs-gateway           # tail just the gateway
make logs-mcp                 # tail just the Plane MCP server
make health                    # scripts/healthcheck.sh
make test                       # gateway unit + integration tests (dockerized, no local Python needed)
make ask QUERY="..."              # scripts/ask-plane.sh
make mobile-run                    # flutter run
make mobile-test                    # flutter test
make mobile-apk                      # reproducible Docker APK build
```

Every `make` target is a thin wrapper -- see `Makefile` for the exact
`docker compose` invocations if you'd rather run them directly.

### CPU vs GPU deployment

CPU is the default and is what the whole stack is verified against. For
GPU-accelerated speech services (requires the NVIDIA Container Toolkit):

```bash
make up GPU=1
```

which adds `-f docker-compose.gpu.yml` to the compose invocation. The core
Plane/MCP/gateway path never depends on a GPU being present. GPU image tags
were confirmed to exist (`docker manifest inspect`) but not runtime-tested
in the environment this stack was built in (no GPU available) -- see
`speech-stt/README.md` and `speech-tts/README.md`.

## API

The gateway exposes a versioned REST API under `/api/v1` -- see
[`gateway/API.md`](gateway/API.md) for the complete, authoritative
reference (every endpoint, request/response shape, and error code). In
development, `http://localhost:8088/docs` also serves live Swagger UI.

### curl examples

```bash
TOKEN=$(grep '^GATEWAY_API_TOKEN=' .env | cut -d= -f2-)

curl http://localhost:8088/api/v1/health

curl -H "Authorization: Bearer $TOKEN" http://localhost:8088/api/v1/health/details

curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "what should I work on now?"}' \
  http://localhost:8088/api/v1/query

curl -H "Authorization: Bearer $TOKEN" \
  -F "file=@recording.m4a" -F "include_audio=true" \
  http://localhost:8088/api/v1/query/audio

curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test."}' \
  http://localhost:8088/api/v1/tts --output speech.mp3
```

## Mobile app

A minimal Flutter Android client lives in `mobile/` -- server setup screen,
text/voice queries, Markdown-rendered answers with copy/speak/retry,
settings (auto-play, voice picker, playback speed, "review transcript
before sending"). It talks **only** to the gateway, never to Plane/MCP/
Whisper/Kokoro/DeepSeek directly, and stores its bearer token in Android's
secure storage.

```bash
cd mobile
flutter pub get
flutter run   # point it at http://10.0.2.2:8088 from an Android emulator
              # (that's the emulator's alias for your host machine), or
              # your machine's real LAN IP from a physical device
```

### Building an APK

```bash
cd mobile
flutter build apk --release
# or, reproducibly via Docker:
docker compose run --rm mobile-build   # -> ./build-output/app-release.apk
```

See `mobile/README.md` for required permissions, the cleartext-traffic
note for local HTTP development, and how to run its test suite
(`flutter test` -- 24 tests covering the API client against mocked HTTP
responses and the server-setup screen).

## Backups

| What | Where | How |
| --- | --- | --- |
| Plane's database | `pgdata` volume | `docker run --rm -v plane-assistant_pgdata:/data -v $PWD:/backup alpine tar czf /backup/pgdata.tar.gz -C /data .` |
| Plane's uploaded files | `uploads` volume | same pattern, volume `plane-assistant_uploads` |
| Gateway conversation history + TTS cache | `gateway_data` volume | same pattern, volume `plane-assistant_gateway_data` (the TTS cache is safe to skip -- it's disposable) |
| Whisper's downloaded model | `whisper-cache` volume | not necessary -- redownloaded automatically |

Restore with the mirror-image `tar xzf ... -C /data`. Always back up
`pgdata` and `uploads` before any upgrade.

## Upgrading

1. Back up (above).
2. Bump the relevant version in `config/versions.env` (and the matching
   component's `.env.example`/`.env`).
3. Read that upstream project's release notes for breaking changes.
4. `docker compose pull && docker compose up -d --build`.
5. `make health` before considering the upgrade done.

For the `plane-mcp` submodule specifically, see `plane-mcp/README.md`'s
"Vendoring / upgrading" section -- it involves checking out a new tag inside
the submodule, not just bumping a compose image tag.

## Troubleshooting

* **`make up` refuses to start** -- `PLANE_WORKSPACE_SLUG`/`PLANE_API_KEY`
  are blank in `.env`; complete Plane's Phase 1 bootstrap first.
* **Gateway starts but `/health/details` shows `"plane": "error"`** -- either
  Plane isn't up yet, or the workspace/API key in `.env` is wrong/revoked.
* **`agent_cli.status` is `"error"`** -- the CLI binary failed its
  `--version` check inside the gateway container; check `make logs-gateway`.
  This does *not* mean your LLM key is bad (that surfaces as
  `LLM_AUTHENTICATION_ERROR` on an actual `/query`, not here).
* **A query returns `MCP_UNAVAILABLE`** -- check `make logs-mcp`; also
  confirm `plane-mcp`'s `PLANE_INTERNAL_BASE_URL` can actually reach Plane's
  `api` service (they must share the `plane-assistant` network, which they
  do by default in the combined stack).
* **Docker Desktop / disk issues** -- if you're on a machine with limited
  disk and Docker's own VM disk fills up, `docker system df` and a scoped
  `docker image prune` (not a blanket `-af` against images you don't
  recognize) is usually the fix; restarting the Docker Desktop daemon
  resolves a wedged state after the underlying disk pressure clears.
* **Android emulator can't reach the gateway** -- use `10.0.2.2`, not
  `localhost`, from the emulator; see `mobile/README.md`.

## Security notes

* `.env` is gitignored; only `.env.example` files are committed. Never
  commit real Plane API keys, DeepSeek keys, gateway tokens, or CLI
  credentials.
* The gateway refuses to start with `GATEWAY_API_TOKEN=change-me` (or blank)
  when `ENVIRONMENT=production` -- see `gateway/app/main.py`.
* The agent CLIs run with `--available-tools plane` (Copilot) /
  `--tools "" --strict-mcp-config --allowedTools mcp__plane__*` (Claude) --
  no shell execution, no arbitrary filesystem access, no web browsing.
  Verified live, not just configured.
* The gateway container runs as a non-root user; nothing mounts the Docker
  socket, `/`, or `~/.ssh` into it.
* The mobile app stores its bearer token in `flutter_secure_storage`, never
  SharedPreferences/logs/source. It never receives the Plane API key or the
  DeepSeek key -- only the gateway does.
* For any deployment reachable outside your own LAN, put a reverse proxy
  (Caddy, Traefik, or Nginx) in front of the gateway and Plane's proxy for
  TLS -- do not send the bearer token over plaintext HTTP on the public
  internet. A minimal Caddy example:

  ```caddyfile
  assistant.example.com {
      reverse_proxy localhost:8088
  }
  plane.example.com {
      reverse_proxy localhost:8080
  }
  ```

## Testing

```bash
make test               # gateway: 72 tests (config, prompts, both agent
                         # adapters' command construction/timeout/output
                         # parsing, sessions, STT/TTS clients, full API
                         # integration tests via FastAPI's TestClient)
make mobile-test         # mobile: 24 tests (API client, server-setup screen)
```

Every component was also verified by actually building and running its
Docker image against the others over the real `plane-assistant` network
(not just unit-tested in isolation) -- e.g. the combined stack's
`docker compose up` was run for real, with the gateway's own
`/api/v1/health/details` confirming it could reach `plane-mcp`, `speech-stt`,
and `speech-tts` by Docker DNS service name. Creating a live Plane account,
a real DeepSeek key, and a physical/emulated Android device to complete
the very last mile (Scenarios 11-12 in the acceptance-test spirit below)
are the parts that need a human running this for real -- everything up to
that boundary has been exercised.

## Non-goals for this MVP

No iOS/desktop app, no custom Jira import, no custom LLM inference engine,
no multi-tenant SaaS/SSO, no real-time token streaming. The architecture
doesn't block adding any of these later -- see each component's own README
for where the seams are (e.g. `AgentCLI`/`SpeechToText`/`TextToSpeech` are
all designed to accept another implementation without touching callers).
