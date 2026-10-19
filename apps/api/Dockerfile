# syntax=docker/dockerfile:1
# EZO API image (Python 3.13 + uv).
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN --mount=type=secret,id=system_ca \
    if [ -f /run/secrets/system_ca ]; then export PIP_CERT=/run/secrets/system_ca; fi; \
    pip install --no-cache-dir uv==0.11.32

WORKDIR /app

# Dependencies first (cached unless pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=system_ca \
    if [ -f /run/secrets/system_ca ]; then export SSL_CERT_FILE=/run/secrets/system_ca; fi; \
    uv sync --frozen --no-dev --no-install-project

# .dockerignore excludes local data, secrets, tests and development environments.
COPY . .
RUN --mount=type=secret,id=system_ca \
    if [ -f /run/secrets/system_ca ]; then export SSL_CERT_FILE=/run/secrets/system_ca; fi; \
    uv sync --frozen --no-dev \
    && chmod -R a+rX /app && chmod 755 /app/entrypoint.sh

FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Keep OCR, Writer and Calc, but ship no package installer or build-tool cache.
# Upgrade packages from the signed Debian repositories; never hide unfixed findings.
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-osd tesseract-ocr-eng tesseract-ocr-rus \
        tesseract-ocr-uzb tesseract-ocr-uzb-cyrl \
        libreoffice-writer-nogui libreoffice-calc-nogui \
        fonts-liberation fonts-dejavu-core libseccomp2 \
    && python -m pip uninstall -y pip \
    && rm -rf /var/lib/apt/lists/* /root/.cache /usr/local/lib/python3.13/ensurepip
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
RUN useradd --create-home --uid 10001 ezo \
    && mkdir -p /app/storage && chown ezo:ezo /app/storage

# Uploaded files live in /app/storage (a Docker volume, see docker-compose.yml).
ENV EZO_STORAGE_DIR=/app/storage
USER ezo

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/api/health', timeout=4)"

# Apply database migrations, then start the API.
CMD ["/app/entrypoint.sh"]

# Only CI targets this stage. Its native tools are identical to the production stage.
FROM runtime AS office-tests
USER root
COPY --from=build /usr/local/bin/uv /usr/local/bin/uv
RUN --mount=type=secret,id=system_ca \
    if [ -f /run/secrets/system_ca ]; then export SSL_CERT_FILE=/run/secrets/system_ca; fi; \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen

# The default image always excludes test/build tools.
FROM runtime AS production
