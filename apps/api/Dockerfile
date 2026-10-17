# EZO API image (Python 3.13 + uv).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app

# Dependencies first (cached unless pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY config ./config
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev

# Uploaded files live in /app/storage (a Docker volume, see docker-compose.yml).
ENV EZO_STORAGE_DIR=/app/storage
RUN useradd --create-home --uid 10001 ezo \
    && mkdir -p /app/storage && chown ezo:ezo /app/storage
USER ezo

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"

# Apply database migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn ezo_api.main:create_app --factory --host 0.0.0.0 --port 8000"]
