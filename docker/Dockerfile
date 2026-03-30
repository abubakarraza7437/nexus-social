# =============================================================================
# SocialOS — Multi-Stage Dockerfile
# =============================================================================
# Stages:
#   base    → installs Python deps (shared layer)
#   api     → Gunicorn + Uvicorn ASGI server
#   worker  → Celery worker (queue selected via QUEUE build arg)
#   beat    → Celery Beat periodic scheduler
#
# Build examples:
#   docker build --target api    -t socialos-api:latest .
#   docker build --target worker -t socialos-worker:latest .
#   docker build --target beat   -t socialos-beat:latest .
# =============================================================================

# -----------------------------------------------------------------------------
# BASE — Python deps + source code
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS base

# Prevent .pyc files and enable unbuffered stdout/stderr (important for logging)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps:
#   libpq-dev   → psycopg2
#   gcc         → C extensions (cryptography, etc.)
#   curl        → healthcheck scripts
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
        curl \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv (fast pip replacement) then install project dependencies.
# uv sync --frozen --no-dev requires uv.lock to exist.
# Run `pip install uv && uv lock` locally to generate it first.
COPY pyproject.toml requirements.txt ./
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Collect static files (WhiteNoise serves them; no media — that's S3)
RUN DJANGO_SETTINGS_MODULE=socialos.settings.production \
    DJANGO_SECRET_KEY=build-time-placeholder \
    DB_HOST=localhost \
    DB_PASSWORD=placeholder \
    TOKEN_ENCRYPTION_KEY=0000000000000000000000000000000000000000000000000000000000000000 \
    python manage.py collectstatic --noinput 2>/dev/null || true

# Non-root user for security
RUN addgroup --system socialos && adduser --system --ingroup socialos socialos
USER socialos

# -----------------------------------------------------------------------------
# API — ASGI server (HTTP + WebSockets)
# -----------------------------------------------------------------------------
FROM base AS api

EXPOSE 8000

# Gunicorn spawns Uvicorn workers for full ASGI support (HTTP + WebSocket).
CMD ["gunicorn", "socialos.asgi:application", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

# -----------------------------------------------------------------------------
# WORKER — Celery task worker
# -----------------------------------------------------------------------------
FROM base AS worker

# Override QUEUE at build time to create queue-specific images, e.g.:
#   docker build --target worker --build-arg QUEUE=publish -t socialos-worker-publish .
ARG QUEUE=publish
ENV QUEUE=${QUEUE}

CMD ["sh", "-c", \
     "celery -A socialos worker -Q ${QUEUE} --concurrency=8 --pool=gevent --loglevel=info"]

# -----------------------------------------------------------------------------
# BEAT — Celery Beat periodic scheduler (single instance only)
# -----------------------------------------------------------------------------
FROM base AS beat

CMD ["celery", "-A", "socialos", "beat", \
     "--scheduler", "django_celery_beat.schedulers:DatabaseScheduler", \
     "--loglevel=info"]
