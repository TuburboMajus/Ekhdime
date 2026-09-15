# Text-to-Speech (Kokoro-FastAPI)

This component wraps [**Kokoro-FastAPI**](https://github.com/remsky/Kokoro-FastAPI),
a Dockerized, OpenAI-API-compatible wrapper around the Kokoro-82M
text-to-speech model, as this stack's text-to-speech service. It does one
job: turn text into spoken audio over HTTP. It has no knowledge of Plane,
the agent CLI, or the gateway -- the gateway's `speech/tts.py` client is the
only thing that calls it.

## How it fits the larger stack

```text
Gateway (FastAPI)
   │  POST http://speech-tts:8880/v1/audio/speech  {"model","input","voice","response_format","speed"}
   ▼
speech-tts  (this component)
   │  Kokoro-82M inference
   ▼
audio bytes (mp3/wav/...)  →  returned to the gateway  →  served to the mobile app
```

The gateway and this service communicate only over the internal
`plane-assistant` Docker network using the service name `speech-tts` -- no
port is published to the host by default, matching this repo's rule that
only Plane's UI and the gateway API should be reachable from outside Docker.

## Verified API surface

These paths and behavior were confirmed by actually running the pinned
image (`ghcr.io/remsky/kokoro-fastapi-cpu:v0.9.0`) and hitting it live, not
assumed from documentation:

### `POST /v1/audio/speech` (OpenAI-compatible)

```bash
curl -X POST http://speech-tts:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
        "model": "kokoro",
        "input": "Hello, this is a test.",
        "voice": "af_heart",
        "response_format": "mp3",
        "speed": 1.0
      }' \
  --output speech.mp3
```

Verified live: this returns `HTTP 200` with a genuine MPEG Layer III audio
file (confirmed with `file speech.mp3` → `MPEG ADTS, layer III, v2, 128
kbps, 24 kHz, Monaural`). `response_format` also accepts `wav`, `opus`,
`flac`, `aac`, and `pcm` per upstream's OpenAI-compatibility claim (not all
individually re-verified here; `mp3`, the gateway's default, was).

### `GET /v1/audio/voices`

Returns available voices. **Verified shape** (this matters -- it is a list
of objects, not bare strings):

```json
{
  "voices": [
    {"id": "af_heart", "name": "af_heart"},
    {"id": "af_alloy", "name": "af_alloy", "target_quality": "B", "overall_grade": "C"},
    ...
  ]
}
```

A live container reported **72 voice packs loaded**. The gateway's
`speech/tts.py` client reduces each entry to its `id` to build the flat
`{"voices": [str, ...]}` list documented in `../gateway/API.md`.

### `GET /health`

```json
{"status": "healthy"}
```

Only reachable once the model has finished warming up -- observed taking
~18 seconds on CPU in this sandbox on first request after startup; the
compose healthcheck's `start_period` accounts for this.

## Model weights: baked in, not downloaded

Unlike Whisper, Kokoro's model weights and all voice packs are **baked into
the image** (confirmed: startup logs load them straight from
`/app/api/src/models` and `/app/api/src/voices`, with no download activity).
This means, unlike `speech-stt`, there is no cache volume to persist here --
nothing is fetched at runtime.

## Running standalone

```bash
cd speech-tts
cp .env.example .env
docker compose up -d --build
docker compose logs -f speech-tts   # wait for "Uvicorn running on http://0.0.0.0:8880"
```

## CPU vs GPU

CPU is the default and what the whole stack assumes works out of the box.
For GPU acceleration (requires the NVIDIA Container Toolkit on the host):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

This switches to `ghcr.io/remsky/kokoro-fastapi-gpu:v0.9.0` (tag existence
confirmed via `docker manifest inspect`, not runtime-tested in this sandbox
since no GPU was available) and reserves an NVIDIA GPU for the container.

## Resource expectations

The CPU image is large (~5GB) because it bundles PyTorch plus all voice
packs; expect a few seconds to ~20s of warmup latency after container start
before the first request succeeds (subsequent requests are fast). No special
RAM tuning is exposed -- there is no `.env` beyond the version pin (see
`.env.example`).
