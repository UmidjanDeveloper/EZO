# syntax=docker/dockerfile:1
# Local isolated document worker (docker compose profile "documents", owner's own PC only).
# It is the trusted controller: it reads queued uploads from PostgreSQL and opens each one in
# its own locked-down executor container (no network, read-only root, 768 MiB, 64 PIDs,
# 25 s, no capabilities, UID 10001) through the Docker socket. Never part of the API image.
ARG API_IMAGE=ezo-api:local
FROM ${API_IMAGE}
USER root
# Only the Docker command-line client (Debian's split package, or the full one as fallback).
RUN apt-get update \
    && (apt-get install -y --no-install-recommends docker-cli \
        || apt-get install -y --no-install-recommends docker.io) \
    && rm -rf /var/lib/apt/lists/*
COPY --chmod=0555 docker/document-worker.sh /usr/local/bin/ezo-document-worker
# The skill worker (profile "skills") uses this same image with its own entrypoint.
COPY --chmod=0555 docker/skill-worker.sh /usr/local/bin/ezo-skill-worker
ENV DOCKER_CONFIG=/tmp/docker
HEALTHCHECK NONE
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/ezo-document-worker"]
CMD []
