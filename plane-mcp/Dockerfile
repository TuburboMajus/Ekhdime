# Official Plane MCP server (Python + FastMCP), built from the vendored
# source at vendor/plane-mcp-server (git submodule pinned to a tag -- see
# ../config/versions.env and README.md "Vendoring" for how to update it).
#
# This mirrors the upstream Dockerfile
# (https://github.com/makeplane/plane-mcp-server/blob/main/Dockerfile)
# almost exactly; the only reason it is copied here rather than referenced
# directly is so this component is self-contained with its own Dockerfile,
# per the repository's per-component layout.
FROM python:3.11-slim

ARG PLANE_MCP_VERSION=v0.3.2
LABEL org.opencontainers.image.title="plane-mcp" \
      org.opencontainers.image.source="https://github.com/makeplane/plane-mcp-server" \
      org.opencontainers.image.version="${PLANE_MCP_VERSION}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY vendor/plane-mcp-server/pyproject.toml ./
COPY vendor/plane-mcp-server/uv.lock ./
COPY vendor/plane-mcp-server/plane_mcp/ ./plane_mcp/

RUN uv pip install --system --no-cache .

RUN useradd --create-home --uid 10001 mcp \
    && chown -R mcp:mcp /app
USER mcp

EXPOSE 8211
ENV FASTMCP_PORT=8211 \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "plane_mcp"]
CMD ["http"]
