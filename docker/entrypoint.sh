#!/usr/bin/env bash
# =============================================================================
# SocialOS — Container Entrypoint
# =============================================================================
# Waits for PostgreSQL and Redis to be ready before executing the CMD.
# Used as ENTRYPOINT in Kubernetes deployments (not in docker-compose where
# depends_on healthchecks handle ordering).
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[entrypoint] $*"; }

wait_for_postgres() {
    log "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
    until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -q; do
        sleep 2
    done
    log "PostgreSQL is ready."
}

wait_for_redis() {
    local host port
    # Parse redis://host:port/db
    host=$(echo "${REDIS_URL}" | sed -E 's|redis://([^:/]+).*|\1|')
    port=$(echo "${REDIS_URL}" | sed -E 's|redis://[^:]+:([0-9]+).*|\1|')
    port="${port:-6379}"

    log "Waiting for Redis at ${host}:${port}..."
    until nc -z "${host}" "${port}" 2>/dev/null; do
        sleep 2
    done
    log "Redis is ready."
}

# ---------------------------------------------------------------------------
# Service checks
# ---------------------------------------------------------------------------
wait_for_postgres
wait_for_redis

# ---------------------------------------------------------------------------
# Database migrations (only for the API/web process — not workers)
# ---------------------------------------------------------------------------
if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
    log "Running database migrations..."
    python manage.py migrate --noinput
    log "Migrations complete."
fi

# ---------------------------------------------------------------------------
# Execute the CMD passed to docker run / Kubernetes pod spec
# ---------------------------------------------------------------------------
log "Starting: $*"
exec "$@"
