# Plane (Community Edition)

This component runs the official, self-hosted **Plane Community Edition**
stack: Postgres, Redis (Valkey), RabbitMQ, MinIO, the Django API/worker/beat
processes, the Next.js web/admin/space frontends, the realtime `live`
service, and the built-in reverse proxy that ties them together and serves
the Plane UI.

Plane is the single source of truth for all project-management data
(projects, issues, cycles, states, comments, assignees...). Nothing in this
repository re-implements any of that -- this component just runs Plane.

## Files

```text
plane/
├── docker-compose.yml   the official release compose, adapted (see below)
├── Dockerfile           wraps makeplane/plane-proxy purely to add a version label
├── .env.example         mirrors the official variables.env
└── README.md
```

There is no vendored source code here: Plane publishes ready-to-run images
(`makeplane/plane-frontend`, `makeplane/plane-backend`, etc.) for every
service. `Dockerfile` only exists so this component has one per this repo's
convention -- see the comment at its top for why it wraps just the proxy
image and nothing else.

## Deviations from upstream

`docker-compose.yml` in this directory starts from the exact file published
at `https://github.com/makeplane/plane/releases/download/v1.4.2/docker-compose.yml`.
The only changes:

1. **Shared network.** Every service joins a `plane-assistant` Docker network
   (instead of the implicit default network) so the `plane-mcp` component --
   run from a separate compose file -- can reach the `api` service by name.
   When this component is combined into the root stack via `include:`, this
   is the same network every other component joins.
2. **Health checks.** Upstream ships no health checks at all. We added
   lightweight ones for `plane-db`, `plane-redis`, `plane-mq`, `plane-minio`
   and `api`, and wired `depends_on: condition: service_healthy` so that,
   for example, `worker`/`beat-worker` don't start hammering an API that
   isn't accepting connections yet, and so the root stack can know when
   Plane itself is actually ready (see root `docker-compose.yml`).
3. **MinIO image.** Upstream uses `minio/minio:latest`. As of building this
   stack, `minio/minio` on Docker Hub rejects anonymous pulls ("pull access
   denied ... may require 'docker login'") -- MinIO restricted anonymous
   access to that repository. We use the equivalent, publicly pullable
   `quay.io/minio/minio` mirror, pinned to a specific `RELEASE.*` tag instead
   of `latest`.
4. **Default host ports.** `LISTEN_HTTP_PORT`/`LISTEN_HTTPS_PORT` default to
   `8080`/`8443` instead of `80`/`443`, so the stack does not require root or
   `CAP_NET_BIND_SERVICE` on a dev machine. Change them back to `80`/`443` in
   `.env` for a production deployment behind nothing else, or leave them as
   non-privileged ports and put a shared reverse proxy in front (see the root
   README's TLS section).

Everything else -- service names, images, environment variable names,
volumes -- is untouched, so upstream upgrade instructions still apply almost
verbatim (see "Upgrading" below).

## Running standalone

```bash
cd plane
cp .env.example .env
# edit .env: at minimum change SECRET_KEY and LIVE_SERVER_SECRET_KEY
docker compose up -d
docker compose ps
```

Plane will be reachable at `http://localhost:8080` (or whatever
`LISTEN_HTTP_PORT` you configured).

Normally, though, you run this as part of the full stack from the repo root
(`make plane-up`), which uses the same file via `include:`.

## Two-phase bootstrap (why Plane starts before the rest of the stack)

The gateway and the Plane MCP server both need a **workspace API key** and a
**workspace slug**. Neither exists until a human has opened Plane, created an
account, and created a workspace. This is why the top-level `Makefile`
separates `make plane-up` from `make up`:

1. **Phase 1 -- `make plane-up`** starts only this component.
2. Open `http://localhost:8080` (or your configured URL) in a browser.
3. Create the first (admin) account.
4. Create a workspace and note its **slug** (the part of the URL after
   `/workspaces/`, e.g. `my-workspace` in `.../my-workspace/projects/`).
5. Go to **Workspace Settings → API tokens** and create a token.
6. Put both values in the repo-root `.env`:
   ```env
   PLANE_WORKSPACE_SLUG=my-workspace
   PLANE_API_KEY=plane_api_xxxxxxxxxxxxxxxx
   ```
7. **Phase 2 -- `make up`** starts everything else (`plane-mcp`, `gateway`,
   `speech-stt`, `speech-tts`), which can now authenticate against your
   workspace. `scripts/bootstrap.sh` and the gateway's own startup checks
   refuse to start Phase 2 services with a clear error if these are still
   blank, rather than starting a half-functional gateway.

## Backups

Everything Plane needs to persist lives in named Docker volumes, all defined
in `docker-compose.yml`:

| Volume | Contents |
| --- | --- |
| `pgdata` | Postgres data directory -- all Plane application data |
| `uploads` | MinIO object storage -- uploaded files/attachments/avatars |
| `redisdata`, `rabbitmq_data` | Cache/queue state -- safe to lose, but backing up avoids a cold restart |
| `logs_*`, `proxy_config`, `proxy_data` | Logs and proxy/TLS state -- not critical |

See the root README's "Backup" section for concrete `docker run --rm -v ...
tar` commands that work across every component in this repository.

## Upgrading

1. Back up `pgdata` and `uploads` (see above).
2. Read the release notes for the target Plane version for any manual
   migration steps.
3. Bump `APP_RELEASE` in `.env` (and `PLANE_VERSION` in `../config/versions.env`).
4. `docker compose pull && docker compose up -d`. The `migrator` service runs
   the Django migrations automatically on every start.
5. Confirm the UI loads and `make health` is green before removing the
   backup.

## Troubleshooting

* **`migrator` keeps restarting** -- check `docker compose logs migrator`;
  this is almost always a Postgres connectivity/credentials problem (check
  `plane-db` is healthy first: `docker compose ps`).
* **Proxy returns 502** -- one of `web`/`api`/`space`/`admin`/`live` is not
  up yet or crashed; check `docker compose ps` and the logs for that service.
* **`plane-minio` unhealthy** -- confirm you can pull
  `quay.io/minio/minio:$MINIO_VERSION` (some networks block quay.io; use a
  registry mirror or point `AWS_S3_ENDPOINT_URL` at your own S3-compatible
  storage instead).
