# Speech-to-Text (Whisper ASR Webservice)

This component wraps the open-source **Whisper ASR Webservice**
([ahmetoner/whisper-asr-webservice](https://github.com/ahmetoner/whisper-asr-webservice),
published on Docker Hub as
[`onerahmet/openai-whisper-asr-webservice`](https://hub.docker.com/r/onerahmet/openai-whisper-asr-webservice))
as this stack's speech-to-text service. It does one job: turn an uploaded
audio file into a text transcript over HTTP. It has no knowledge of Plane,
the agent CLI, or the gateway -- the gateway's `speech/stt.py` client is the
only thing that calls it.

## How it fits the larger stack

```text
Gateway (FastAPI)
   │  POST http://speech-stt:9000/asr  (multipart/form-data, audio_file=...)
   ▼
speech-stt  (this component)
   │  faster-whisper model inference
   ▼
transcript text  →  returned to the gateway  →  fed into the prompt builder
```

The gateway and this service communicate only over the internal
`plane-assistant` Docker network using the service name `speech-stt` -- no
port is published to the host by default, matching this repo's rule that
only Plane's UI and the gateway API should be reachable from outside Docker.

## Verified API surface

These paths and parameters were confirmed by actually running the pinned
image and reading `GET /openapi.json` and `GET /docs` (Swagger UI) on a live
container, plus upstream's `docs/endpoints.md`:

### `POST /asr`

Multipart form upload. Query parameters (all optional except the file):

| Param             | Values                                              | Default      | Notes                                   |
|-------------------|------------------------------------------------------|--------------|------------------------------------------|
| `audio_file`       | file (form field)                                    | required     | Converted via ffmpeg automatically       |
| `output`           | `txt`, `json`, `vtt`, `srt`, `tsv`                    | `txt`        | Response format                          |
| `task`             | `transcribe`, `translate`                             | `transcribe` | `translate` always outputs English       |
| `language`         | ISO 639-1 code (e.g. `en`, `fr`, `tr`, ...)            | auto-detect  | Full list served in the OpenAPI schema   |
| `word_timestamps`  | `true` / `false`                                       | `false`      | faster-whisper only                      |
| `vad_filter`       | `true` / `false`                                       | `false`      | Voice-activity filtering, faster-whisper only |
| `encode`           | `true` / `false`                                       | `true`       | Pre-encode audio through ffmpeg          |
| `initial_prompt`   | string                                                 | none         | Optional priming text                    |

Example (verified working against a live container in this environment):

```bash
curl -X POST -H "content-type: multipart/form-data" \
  -F "audio_file=@/path/to/file.wav" \
  "http://speech-stt:9000/asr?output=json"
```

### `POST /detect-language`

Detects the spoken language from the first 30 seconds of an uploaded file.
Returns `{"detected_language": "...", "language_code": "...", "confidence": 0.0-1.0}`.

### `GET /docs`, `GET /openapi.json`

Interactive Swagger UI / OpenAPI schema -- confirmed served by the pinned
`v1.10.0` image and used as this component's Docker healthcheck target.

## Environment variables

See [`.env.example`](.env.example) for the full, individually-sourced list.
Summary of the ones you're most likely to touch:

| Variable          | Default (this repo) | Upstream default | Purpose                                             |
|-------------------|----------------------|-------------------|------------------------------------------------------|
| `ASR_ENGINE`       | `faster_whisper`      | `openai_whisper`  | This repo pins faster-whisper per its own design goal |
| `ASR_MODEL`        | `small`               | `base`            | `tiny\|base\|small\|medium\|large-v3\|...`            |
| `ASR_MODEL_PATH`   | (blank)               | `~/.cache/whisper`| Override model storage location                     |
| `ASR_DEVICE`       | `cpu`                 | auto (`cuda` if available) | Forced to `cpu` here; GPU override sets `cuda`|
| `ASR_QUANTIZATION` | `int8`                | `int8` (CPU) / `float32` (GPU) | Weight precision                       |
| `MODEL_IDLE_TIMEOUT` | `0`                 | `0`               | Seconds idle before unloading model (0 = never)     |
| `SAMPLE_RATE`      | `16000`               | `16000`           | Expected input sample rate                          |
| `HF_TOKEN`         | (blank)               | (blank)           | Only needed if `ASR_ENGINE=whisperx`                |

Every variable is read directly by upstream's `app/config.py` at v1.10.0 --
nothing here is invented.

## Running standalone

```bash
cd speech-stt
cp .env.example .env
docker compose up -d --build
```

This builds the local `Dockerfile` (which just re-tags the pinned upstream
image with an OCI label), starts the container on a project-scoped
`plane-assistant` network, and waits for the healthcheck (`curl -f
http://localhost:9000/docs` inside the container) to pass.

Because no port is published by default, test it from another container on
the same network rather than from the host:

```bash
docker run --rm --network plane-assistant curlimages/curl:latest \
  -s -o /dev/null -w '%{http_code}\n' http://speech-stt:9000/docs
# -> 200
```

or exec into the running container directly:

```bash
docker compose exec speech-stt curl -s http://localhost:9000/openapi.json | head -c 200
```

Tear down with:

```bash
docker compose down
```

(the `whisper-cache` named volume is preserved across `down`/`up`; add `-v`
only if you intentionally want to force a re-download of models.)

## Swapping models via `.env`

Edit `ASR_MODEL` in `.env` and recreate the container:

```bash
# e.g. switch to a larger, more accurate model
sed -i 's/^ASR_MODEL=.*/ASR_MODEL=medium/' .env
docker compose up -d
```

The new model downloads into the `whisper-cache` volume on first use and is
reused on subsequent restarts (see "Model cache" below). Valid values
(verified against upstream's `docs/environmental-variables.md` for v1.10.0):

- Standard: `tiny`, `base`, `small`, `medium`, `large-v1`, `large-v2`,
  `large-v3` (alias `large`), `large-v3-turbo` (alias `turbo`)
- English-optimized: `tiny.en`, `base.en`, `small.en`, `medium.en`
- Distilled (faster_whisper/whisperx only): `distil-large-v2`,
  `distil-medium.en`, `distil-small.en`, `distil-large-v3`

## Model cache (persisted volume)

Verified by actually running the pinned image with `ASR_MODEL=tiny` and
`ASR_ENGINE=faster_whisper` and inspecting the filesystem afterward:
downloaded model files land under `/root/.cache/whisper` (a
HuggingFace-hub-style layout, e.g.
`/root/.cache/whisper/models--Systran--faster-whisper-tiny/...`), with
`/root/.cache/huggingface` also populated. The container runs as `root`
(`HOME=/root`), confirmed via `docker exec ... id`.

This matches upstream's own `docker-compose.yml`/`docker-compose.gpu.yml`,
which mount a named volume at `/root/.cache` for exactly this reason. This
component's `docker-compose.yml` does the same:

```yaml
volumes:
  - whisper-cache:/root/.cache
```

so models survive `docker compose down` / `up` and are only re-downloaded
when you change `ASR_MODEL` to a size not already cached, or explicitly wipe
the volume (`docker compose down -v`).

## CPU vs GPU

CPU is the default and requires no extra setup:

```bash
docker compose up -d --build
```

For NVIDIA GPU acceleration, layer the optional override (requires the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
on the Docker host):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

This switches the base image to the `-gpu` variant of the same pinned
version (`onerahmet/openai-whisper-asr-webservice:v1.10.0-gpu` -- confirmed
to exist via the Docker Hub tags API before referencing it) and reserves one
NVIDIA GPU via `deploy.resources.reservations.devices`. It also switches
`ASR_DEVICE` to `cuda` and `ASR_QUANTIZATION` to `float16`.

**Not runtime-tested**: this sandbox has no GPU, so the `docker-compose.gpu.yml`
override was verified for correctness (image tag exists, compose syntax,
matches the `deploy.resources.reservations` shape this repo's conventions
call for) but never actually started against real GPU hardware.

## Resource expectations (approximate)

Whisper/faster-whisper model files on disk (int8 CTranslate2 weights,
confirmed via HTTP `Content-Length` against the actual
`Systran/faster-whisper-*` model files used by the `faster_whisper` engine)
give a reasonable floor for RAM usage; the running container needs somewhat
more for the Python/ffmpeg/uvicorn process itself:

| `ASR_MODEL` | Model weights on disk (int8) | Rough RAM to budget (CPU, int8) |
|-------------|-------------------------------|-----------------------------------|
| `tiny`      | ~72 MB                        | ~1 GB                             |
| `base`      | ~139 MB                       | ~1 GB                             |
| `small`     | ~461 MB                       | ~2 GB                             |
| `medium`    | ~1.4 GB                       | ~5 GB                             |
| `large-v3`  | ~2.9 GB                       | ~8-10 GB                          |

These are rough planning numbers, not guaranteed limits -- actual usage
depends on concurrent requests, audio length, and whether VAD/word
timestamps are enabled. The default `ASR_MODEL=small` with
`ASR_ENGINE=faster_whisper` and `ASR_QUANTIZATION=int8` is a reasonable
default for a small CPU host; GPU deployments can comfortably run larger
models.

## What was verified by actually running this component

- Pulled and inspected `onerahmet/openai-whisper-asr-webservice:v1.10.0`
  directly (`docker image inspect`): exposed port `9000/tcp`, working
  directory `/app`, entrypoint `whisper-asr-webservice`, runs as root.
- Confirmed `curl` and `wget` are both present inside the image
  (`docker run --entrypoint sh ... which curl wget python3`), so the
  healthcheck in `docker-compose.yml` uses `curl` directly with no extra
  install step.
- Ran the container with `ASR_MODEL=tiny ASR_ENGINE=faster_whisper`, waited
  for `GET /docs` to return `200`, then inspected the filesystem and found
  the downloaded model under `/root/.cache/whisper/models--Systran--faster-whisper-tiny/`.
- Fetched `GET /openapi.json` from the live container and confirmed the
  real route list (`POST /asr`, `POST /detect-language`) and the full
  `/asr` query-parameter schema.
- Fetched upstream's own `docker-compose.yml`, `docker-compose.gpu.yml`,
  `app/config.py`, `Dockerfile`, `Dockerfile.gpu`, and
  `docs/environmental-variables.md` at the current `main` branch to
  cross-check every environment variable and the `/root/.cache` volume
  mount pattern used in this component's compose files.
- Queried the Docker Hub tags API for
  `onerahmet/openai-whisper-asr-webservice` and confirmed `v1.10.0-gpu`
  exists before referencing it in `docker-compose.gpu.yml`.
- Built and started this component's own `docker-compose.yml` standalone
  and confirmed the container reaches a healthy state and responds
  correctly on its internal port (see the file history/PR for the exact
  session), then tore it down with `docker compose down`.

**Not verified** (documented, not tested): actual GPU execution of
`docker-compose.gpu.yml` (no GPU hardware in this environment), and
`whisperx`-specific behavior (diarization, `HF_TOKEN` usage) since this
repo's default engine is `faster_whisper`.
