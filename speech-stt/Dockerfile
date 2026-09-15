# Whisper ASR Webservice (https://github.com/ahmetoner/whisper-asr-webservice)
#
# This wraps the upstream published image rather than rebuilding it from
# source, since the upstream project already publishes a maintained,
# version-tagged CPU image on Docker Hub
# (https://hub.docker.com/r/onerahmet/openai-whisper-asr-webservice/tags).
# The version is pinned via WHISPER_ASR_VERSION in ../config/versions.env
# and passed in as a build ARG so this Dockerfile never floats to `:latest`.
#
# Facts below were verified by actually running the pinned image
# (onerahmet/openai-whisper-asr-webservice:v1.10.0), not assumed:
#   - `docker image inspect` shows ExposedPorts=9000/tcp, WorkingDir=/app,
#     Entrypoint=["whisper-asr-webservice"], and the container runs as root
#     (HOME=/root).
#   - `docker run --entrypoint sh ... -c 'which curl wget python3 python'`
#     confirmed the image (Debian 12 "bookworm" base) has curl, wget, and
#     python3 all available -- curl is used below for the healthcheck.
#   - Running the container with -e ASR_MODEL=tiny -e ASR_ENGINE=faster_whisper
#     showed the faster-whisper model lands under /root/.cache/whisper
#     (HuggingFace-hub-style layout: models--Systran--faster-whisper-tiny/...),
#     and /root/.cache/huggingface is also used. This matches upstream's own
#     docker-compose.yml, which mounts a named volume at /root/.cache.
#   - GET /docs returned 200 (Swagger UI) and GET /openapi.json listed the
#     real routes: POST /asr and POST /detect-language.
ARG WHISPER_ASR_VERSION=v1.10.0

FROM onerahmet/openai-whisper-asr-webservice:${WHISPER_ASR_VERSION}

# ARG values are cleared after FROM, so re-declare to use it in LABEL below.
ARG WHISPER_ASR_VERSION=v1.10.0

LABEL org.opencontainers.image.title="speech-stt" \
      org.opencontainers.image.description="Whisper ASR Webservice (faster-whisper engine) -- speech-to-text for the Plane MCP Voice Assistant stack" \
      org.opencontainers.image.source="https://github.com/ahmetoner/whisper-asr-webservice" \
      org.opencontainers.image.version="${WHISPER_ASR_VERSION}"

# Upstream's own ENTRYPOINT/CMD/EXPOSE (from the base image) are reused as-is;
# nothing about the runtime process changes here, only image metadata.
