# Plane publishes ready-to-run official images for every service in this
# component (makeplane/plane-frontend, plane-backend, plane-admin,
# plane-space, plane-live, plane-proxy) -- there is no first-party source to
# build here, and forking Plane's own build process would violate this
# repo's "do not unnecessarily fork Plane's Docker configuration" rule (see
# README.md "Deviations from upstream").
#
# This Dockerfile exists so the component still has one, per this
# repository's convention (every component owns its Dockerfile/.env.example/
# docker-compose.yml) -- it wraps the one image a human actually looks at
# (the reverse proxy serving the Plane UI) purely to attach a version label,
# the same "wrap + label" pattern used by speech-stt/Dockerfile and
# speech-tts/Dockerfile for their own upstream images. It changes nothing
# about the running process. The other Plane services in docker-compose.yml
# (plane-db, plane-redis, plane-mq, plane-minio, api/worker/beat-worker/
# migrator, web, admin, space, live) reference upstream images directly --
# building a Dockerfile for each would just be duplication for its own sake.
ARG APP_RELEASE=v1.4.2

FROM makeplane/plane-proxy:${APP_RELEASE}

ARG APP_RELEASE=v1.4.2
LABEL org.opencontainers.image.title="plane-proxy" \
      org.opencontainers.image.source="https://github.com/makeplane/plane" \
      org.opencontainers.image.version="${APP_RELEASE}"
