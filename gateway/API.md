# Gateway API contract (v1)

This is the authoritative contract implemented by `app/api/*.py` and consumed
by `mobile/` and `scripts/ask-plane.sh`. All endpoints live under `/api/v1`,
per the root README's API-versioning rule.

Base URL: whatever `GATEWAY_HOST:GATEWAY_PORT` resolves to, e.g.
`http://localhost:8088` in development.

## Authentication

Every endpoint requires `Authorization: Bearer <GATEWAY_API_TOKEN>` **except**:

* `GET /api/v1/health`
* `GET /api/v1/info`

These two are safe to call before the client has a token configured (e.g. to
render a "server reachable, now enter your token" state), and return no
secrets.

## Error envelope

Any non-2xx response uses:

```json
{
  "error": {
    "code": "AGENT_TIMEOUT",
    "message": "The AI agent did not complete within 180 seconds.",
    "request_id": "b3b9c3d0-..."
  }
}
```

| Code | HTTP status | Meaning |
| --- | --- | --- |
| `UNAUTHORIZED` | 401 | Missing/invalid bearer token |
| `INVALID_REQUEST` | 400 | Malformed body/query/multipart field |
| `NOT_FOUND` | 404 | Conversation/resource does not exist |
| `AUDIO_TOO_LARGE` | 413 | Upload exceeds `MAX_AUDIO_SIZE_MB`/`MAX_AUDIO_DURATION_SECONDS` |
| `STT_UNAVAILABLE` | 503 | Whisper service unreachable/erroring |
| `TTS_UNAVAILABLE` | 503 | Kokoro service unreachable/erroring |
| `MCP_UNAVAILABLE` | 503 | Plane MCP server unreachable |
| `PLANE_UNAVAILABLE` | 503 | Plane itself unreachable, or workspace not bootstrapped yet |
| `AGENT_UNAVAILABLE` | 503 | Copilot/Claude CLI missing or failed to start |
| `AGENT_TIMEOUT` | 504 | CLI subprocess exceeded `AGENT_TIMEOUT_SECONDS` |
| `AGENT_INVALID_RESPONSE` | 502 | Model produced malformed/leaked tool-call syntax instead of a real answer |
| `EMPTY_TRANSCRIPT` | 400 | Whisper found no speech in the uploaded audio |
| `LLM_AUTHENTICATION_ERROR` | 502 | LLM provider rejected credentials |
| `LLM_RATE_LIMITED` | 429 | LLM provider rate-limited the request |
| `INTERNAL_ERROR` | 500 | Anything else unexpected |

`POST /query/audio` specifically: if transcription succeeds but everything
after it fails (agent error, cancellation), the error response carries the
already-transcribed text as a sibling `transcript` field so the client can
still show what the user said instead of losing it behind a bare error:

```json
{
  "error": {
    "code": "AGENT_INVALID_RESPONSE",
    "message": "...",
    "request_id": "b3b9c3d0-..."
  },
  "transcript": "what the user actually said"
}
```

`transcript` is absent when the failure happened before or during
transcription itself (e.g. `EMPTY_TRANSCRIPT`, `STT_UNAVAILABLE`) -- there is
nothing to show in that case.

## Endpoints

### `GET /api/v1/health`

No auth. Liveness only.

```json
{"status": "ok"}
```

### `GET /api/v1/info`

No auth. Capability discovery for clients that haven't configured a token
yet.

```json
{
  "server_version": "0.1.0",
  "api_version": "v1",
  "features": {
    "stt": true,
    "tts": true,
    "conversations": true,
    "request_cancellation": true
  }
}
```

### `GET /api/v1/health/details`

Auth required.

```json
{
  "gateway": "ok",
  "plane": "ok",
  "plane_mcp": "ok",
  "stt": "ok",
  "tts": "ok",
  "agent_cli": {"status": "ok", "type": "copilot"}
}
```

Each of `plane`/`plane_mcp`/`stt`/`tts`/`agent_cli.status` is `"ok"` or
`"error"`; never fabricated. `plane` is checked with a direct, read-only
Plane REST call (allowed per the "infrastructure health checks may call
Plane directly" design rule) -- this is the one place in the codebase that
calls Plane's API without going through MCP.

### `POST /api/v1/query`

Auth required.

Request:

```json
{"query": "list all my projects", "conversation_id": null, "include_audio": false}
```

Response:

```json
{
  "request_id": "8f14e...",
  "conversation_id": "b3b9c...",
  "query": "list all my projects",
  "answer": "You currently have three projects...",
  "agent": {"cli": "copilot", "model": "deepseek-v4-pro"},
  "audio": null,
  "duration_ms": 3240,
  "reasoning": "The user wants a project list. I'll call list_projects."
}
```

`reasoning` is the model's chain-of-thought for this turn, when the CLI/model
produced one (`null` otherwise). It is kept separate from `answer` on
purpose -- clients should render it as a collapsed-by-default "Thinking"
section (see `mobile/lib/widgets/message_bubble.dart`), not mix it into the
visible response.

If `include_audio: true` and synthesis succeeds:

```json
"audio": {"available": true, "url": "/api/v1/audio/responses/8f14e...", "mime_type": "audio/mpeg"}
```

If `conversation_id` is omitted/null, a new conversation is created and its id
returned.

### `POST /api/v1/query/audio`

Auth required. `multipart/form-data` fields: `file` (required),
`conversation_id` (optional), `include_audio` (optional, `"true"`/`"false"`,
default `"false"`), `language` (optional, ISO-639-1 code; omitted = auto
detect).

Response:

```json
{
  "request_id": "8f14e...",
  "conversation_id": "b3b9c...",
  "transcript": "What task should I do now?",
  "answer": "The most useful task to start now is...",
  "agent": {"cli": "copilot", "model": "deepseek-v4-pro"},
  "audio": {"available": true, "url": "/api/v1/audio/responses/8f14e...", "mime_type": "audio/mpeg"},
  "reasoning": "The user wants a next-task recommendation. I'll check assignments, priority, and due dates."
}
```

`reasoning` has the same meaning as in `POST /api/v1/query` above.

The transcript is always returned so the client can show "You said: ...".

### `POST /api/v1/stt`

Auth required. `multipart/form-data`: `file` (required), `language`
(optional). Runs Whisper only -- no agent/Plane call. Used by the optional
"review transcript before sending" flow.

```json
{"text": "Move task ABC-42 to done"}
```

### `POST /api/v1/tts`

Auth required.

Request:

```json
{"text": "The highest priority task is ABC-42.", "voice": null, "format": "mp3", "speed": 1.0}
```

Response: raw audio bytes with `Content-Type: audio/mpeg` (or the
corresponding type for the requested format). `voice: null` uses
`TTS_VOICE` from server config.

### `GET /api/v1/tts/voices`

Auth required. Lets clients populate a voice picker without hard-coding a
list.

```json
{"voices": ["af_heart", "af_bella", "am_adam"], "default": "af_heart"}
```

### `GET /api/v1/audio/responses/{id}`

Auth required. Returns the cached synthesized audio referenced by a previous
`query`/`query/audio` response's `audio.url`. `404 NOT_FOUND` once evicted
(see `TTS_CACHE_TTL_SECONDS`).

### `GET /api/v1/conversations`

Auth required.

```json
{"conversations": [{"id": "b3b9c...", "title": "Sprint planning", "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-01T10:05:00Z"}]}
```

### `POST /api/v1/conversations`

Auth required. Body: `{"title": null}` (title optional). Returns `201` with
the created conversation (same shape as a list item, no `messages`).

### `GET /api/v1/conversations/{id}`

Auth required.

```json
{
  "id": "b3b9c...",
  "title": "Sprint planning",
  "created_at": "2026-09-01T10:00:00Z",
  "updated_at": "2026-09-01T10:05:00Z",
  "messages": [
    {"id": "1...", "role": "user", "content": "What should I work on today?", "created_at": "...", "metadata": {}},
    {"id": "2...", "role": "assistant", "content": "ABC-42.", "created_at": "...", "metadata": {"tools_used": ["plane.list_issues"]}}
  ]
}
```

`404 NOT_FOUND` if the id does not exist.

### `DELETE /api/v1/conversations/{id}`

Auth required. `204` on success (idempotent: also `204` if it already didn't
exist, to keep client retry logic simple).

### `DELETE /api/v1/requests/{id}`

Auth required. Best-effort cancellation of an in-flight `query`/`query/audio`
call sharing that `request_id`. `202 {"cancelled": true|false}`.

## Notes for client implementers

* Always send `Accept: application/json` except when expecting raw audio
  bytes back (`/tts`, `/audio/responses/{id}`).
* `duration_ms` and per-stage timings are for observability/UI ("thinking...
  3.2s"), not for correctness -- never branch client logic on them.
* The mobile app never talks to Plane, the MCP server, Whisper, or Kokoro
  directly -- only to this gateway, and only with the bearer token, per the
  root README's design principles.
