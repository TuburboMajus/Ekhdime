# Plane MCP Server

This component builds and runs Plane's **official** Model Context Protocol
server (the Python + FastMCP implementation at
[makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server),
*not* the deprecated Node package). It is the only thing in this repository
that is allowed to translate natural-language intent into Plane API calls on
behalf of an AI agent -- see the root README's design principles.

## Files

```text
plane-mcp/
├── Dockerfile                  builds the vendored server, mirrors upstream's own Dockerfile
├── docker-compose.yml          runs it on the shared `plane-assistant` network
├── docker-compose.expose.yml   optional override to publish the port to the host
├── .env.example
├── vendor/plane-mcp-server/    git submodule, pinned to v0.3.2
└── README.md
```

## How authentication actually works (read this before changing env vars)

This took reading the actual server source
(`plane_mcp/__main__.py`, `plane_mcp/server.py`,
`plane_mcp/auth/plane_header_auth_provider.py`,  `plane_mcp/client.py`) to
get right, because the hosted-service docs describe a different (OAuth,
multi-tenant) setup than what a single-workspace self-host needs. The facts,
verified against the pinned `v0.3.2` source:

* Running `python -m plane_mcp http` (this container's default command)
  starts **three** mounted sub-apps in one process:
  * `/http/mcp` -- OAuth-authenticated (needs a registered OAuth client;
    irrelevant for us).
  * `/sse` -- deprecated SSE transport.
  * **`/http/api-key/mcp`** -- the one this stack uses.
* `PlaneHeaderAuthProvider` (the auth class behind that route) extends
  FastMCP's `TokenVerifier`, whose contract is standard OAuth2 **Bearer
  Token** auth (RFC 6750): the credential must arrive as
  **`Authorization: Bearer <PLANE_API_KEY>`**, extracted by FastMCP's own
  transport layer before `verify_token()` is ever called.
  `x-workspace-slug` is a second, genuinely custom header that
  `verify_token()` reads directly off the request itself. **An earlier
  version of this doc (and of `gateway/app/plane/mcp.py`) got this wrong**,
  sending the API key as a custom `x-api-key` header instead -- that
  reaches FastMCP's auth middleware as "no Authorization header at all", so
  every connection silently sat at MCP status `needs-auth` forever. Found
  by watching a real Copilot CLI session hallucinate a fake `bash` tool
  call because it had never actually seen any real Plane tools (the MCP
  connection had never succeeded), then confirmed with two live curl calls
  against the running container -- `x-api-key` alone: `401 invalid_token`;
  `Authorization: Bearer <key>`: a real `200` `initialize` response listing
  actual tools. The `x-api-key` header *does* separately exist, but only
  one hop further downstream -- see below.
* Once verified, `verify_token()` validates the bearer token with a live
  call to `{PLANE_INTERNAL_BASE_URL or PLANE_BASE_URL}/api/v1/users/me/`,
  **re-packaged as Plane's own `x-api-key` header for that one call** --
  this is an internal implementation detail of how plane-mcp talks to
  Plane, unrelated to what a client must send to plane-mcp itself. There is
  **no** container-level `PLANE_API_KEY`/`PLANE_WORKSPACE_SLUG` for HTTP
  mode -- those only apply to `stdio` mode. Every tool call after that
  reuses the same header-derived credentials (`plane_mcp/client.py`), so
  this container never stores or needs the workspace's API key itself.
* This means the plane-mcp container's own `.env` only needs to know **where
  Plane is** (`PLANE_INTERNAL_BASE_URL`); the **who** (API key, workspace
  slug) is supplied per-request by whoever calls it -- in this stack, the
  gateway, when it generates a throwaway MCP client config for each Copilot
  or Claude CLI invocation (see `gateway/app/plane/mcp.py`).

Full endpoint, from inside the Docker network:

```text
http://plane-mcp:8211/http/api-key/mcp
Headers:
  Authorization: Bearer <PLANE_API_KEY>
  x-workspace-slug: <PLANE_WORKSPACE_SLUG>
```

**Startup quirk found by actually running the container** (not documented
upstream): `python -m plane_mcp http` constructs the OAuth transport
*unconditionally*, even though we never use it, and its constructor raises
`ValueError` if `PLANE_OAUTH_PROVIDER_CLIENT_ID`/`_CLIENT_SECRET` are unset,
and separately raises if the derived issuer URL isn't HTTPS (or localhost).
`docker-compose.yml` sets harmless placeholder values
(`PLANE_OAUTH_PROVIDER_CLIENT_ID=unused`, etc. -- see `.env.example`) purely
so the process boots; no OAuth client anywhere in this stack ever uses them.

## Vendoring / upgrading

The server source lives at `vendor/plane-mcp-server` as a **git submodule**
pinned to a tag, not a moving branch:

```bash
git submodule update --init plane-mcp/vendor/plane-mcp-server

# to upgrade to a newer tag later:
cd plane-mcp/vendor/plane-mcp-server
git fetch --tags
git checkout <new-tag>
cd -
git add plane-mcp/vendor/plane-mcp-server
# update PLANE_MCP_VERSION in plane-mcp/.env.example and config/versions.env
docker compose build plane-mcp
```

Before bumping the version, diff `plane_mcp/auth/plane_header_auth_provider.py`
and `plane_mcp/server.py` against the notes above -- the header-auth route
path or header names are an implementation detail of the upstream project
and could change between releases.

## Running standalone

The server needs a running Plane instance to be useful, so standalone usage
is mostly for confirming the image builds and boots:

```bash
cd plane-mcp
git submodule update --init vendor/plane-mcp-server
cp .env.example .env
docker compose up -d --build
docker compose logs -f plane-mcp
```

To test it end-to-end you need the `plane` component's `plane-assistant`
network up too (`cd ../plane && docker compose up -d`), since
`PLANE_INTERNAL_BASE_URL` resolves `api` via Docker DNS on that network.

## Testing connectivity manually

With the full stack up and a real Plane API key + workspace slug:

```bash
curl -i http://localhost:8100/http/api-key/mcp \
  -H "Authorization: Bearer $PLANE_API_KEY" \
  -H "x-workspace-slug: $PLANE_WORKSPACE_SLUG" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

(`PLANE_MCP_EXPOSE_PORT=true` must be set for port `8100` to be published to
the host -- see `.env.example`.) A `200`/`text/event-stream` response with an
`initialize` result confirms Plane, the network, and the header-auth path all
work. `scripts/healthcheck.sh` in the repo root automates a simplified
version of this check.

## Restricting what the agent can do

This container exposes **all** Plane MCP tools (reads and writes) to
whichever CLI connects to it -- Plane-side scoping is only as fine as the API
key's own permissions. The read/write split described in the root README's
"Destructive Operations" section is enforced by the **gateway and the system
prompt**, not by this component. If Plane ever supports read-only API keys,
generating one for a "safe mode" deployment would be a good enhancement here.
