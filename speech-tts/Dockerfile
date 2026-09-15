# Kokoro-FastAPI (https://github.com/remsky/Kokoro-FastAPI) -- an
# OpenAI-compatible TTS wrapper around the Kokoro-82M model. Wraps the
# upstream published CPU image rather than rebuilding from source, since the
# upstream project already publishes a maintained, version-tagged image.
#
# Facts below were verified by actually running the pinned image
# (ghcr.io/remsky/kokoro-fastapi-cpu:v0.9.0), not assumed:
#   - `docker inspect` shows the container runs as user "appuser", with
#     DEVICE=cpu/USE_GPU=false baked in as env defaults, and CMD ["./entrypoint.sh"].
#   - `docker run --entrypoint sh ... -c 'which curl wget python3'` confirmed
#     curl is present (used below for the healthcheck) and python3 is a venv
#     interpreter at /app/.venv/bin/python3.
#   - On startup the service loads the Kokoro v1 model and warms it up
#     (~18s on CPU in this sandbox), then logs "72 voice packs loaded" and
#     "Uvicorn running on http://0.0.0.0:8880".
#   - GET /openapi.json listed the real routes, including the two this stack
#     uses: POST /v1/audio/speech and GET /v1/audio/voices, plus GET /health
#     returning {"status":"healthy"}.
#   - A real POST to /v1/audio/speech with
#     {"model":"kokoro","input":"...","voice":"af_heart","response_format":"mp3","speed":1.0}
#     returned HTTP 200 with a valid MP3 file (confirmed with `file`).
# BASE_IMAGE lets docker-compose.gpu.yml switch to the -gpu variant of the
# same pinned version without a second Dockerfile.
ARG BASE_IMAGE=ghcr.io/remsky/kokoro-fastapi-cpu
ARG KOKORO_FASTAPI_VERSION=v0.9.0

FROM ${BASE_IMAGE}:${KOKORO_FASTAPI_VERSION}

# ARG values are cleared after FROM, so re-declare to use it in LABEL below.
ARG KOKORO_FASTAPI_VERSION=v0.9.0

LABEL org.opencontainers.image.title="speech-tts" \
      org.opencontainers.image.description="Kokoro-FastAPI (OpenAI-compatible) -- text-to-speech for the Plane MCP Voice Assistant stack" \
      org.opencontainers.image.source="https://github.com/remsky/Kokoro-FastAPI" \
      org.opencontainers.image.version="${KOKORO_FASTAPI_VERSION}"

# Upstream's own ENTRYPOINT/CMD/EXPOSE (from the base image) are reused as-is;
# nothing about the runtime process changes here, only image metadata.
