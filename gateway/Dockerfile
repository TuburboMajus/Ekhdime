# Gateway: FastAPI orchestrator + the two agent CLIs it can shell out to.
#
# Node.js is only needed to install the Copilot/Claude CLIs (both ship as npm
# packages); ffmpeg is only needed for `ffprobe`, used to enforce
# MAX_AUDIO_DURATION_SECONDS (see app/speech/probe.py).
FROM python:3.11-slim

ARG COPILOT_CLI_VERSION=1.0.83
ARG CLAUDE_CODE_VERSION=2.1.270

LABEL org.opencontainers.image.title="plane-assistant-gateway"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg ffmpeg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verified real, pinned npm packages -- see the root README's "Copilot CLI" /
# "Claude Code" research notes for how these flags/env vars were confirmed.
RUN npm install -g \
        "@github/copilot@${COPILOT_CLI_VERSION}" \
        "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 gateway \
    && mkdir -p /home/gateway/.copilot-home /home/gateway/.claude-home /data/tts-cache \
    && chown -R gateway:gateway /home/gateway /app /data

# No shell, no filesystem writes beyond /data, no Docker socket, no host
# filesystem -- see root README section 14 "Restrict Agent Capabilities".
USER gateway

ENV PYTHONUNBUFFERED=1 \
    HOME=/home/gateway

EXPOSE 8088

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8088/api/v1/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
