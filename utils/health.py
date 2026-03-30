"""
Utils — Health & Readiness Check Views
=========================================
Used by Kubernetes liveness and readiness probes.

GET /health/   → liveness  — returns 200 if the process is alive (no DB)
GET /ready/    → readiness — returns 200 when DB, Redis, Celery are reachable
"""

import logging

from django.db import connection
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


class HealthView(View):
    """
    Liveness probe — confirms the Python process is alive and Django is loaded.
    Intentionally does NOT check external services so a DB outage doesn't
    trigger a pod restart loop.
    """

    def get(self, request, *args, **kwargs) -> JsonResponse:
        return JsonResponse({"status": "ok"}, status=200)


class ReadinessView(View):
    """
    Readiness probe — confirms all critical dependencies are reachable.
    Kubernetes stops sending traffic to the pod if this returns non-200.
    """

    def get(self, request, *args, **kwargs) -> JsonResponse:
        checks = {
            "db": self._check_db(),
            "redis": self._check_redis(),
            "celery": self._check_celery(),
        }
        all_ok = all(checks.values())
        status_code = 200 if all_ok else 503
        return JsonResponse(
            {"status": "ok" if all_ok else "degraded", "checks": checks},
            status=status_code,
        )

    def _check_db(self) -> bool:
        try:
            connection.ensure_connection()
            return True
        except Exception:
            logger.exception("Readiness: DB check failed")
            return False

    def _check_redis(self) -> bool:
        try:
            from django.core.cache import cache

            cache.set("_readiness_probe", "1", timeout=5)
            return cache.get("_readiness_probe") == "1"
        except Exception:
            logger.exception("Readiness: Redis check failed")
            return False

    def _check_celery(self) -> bool:
        try:
            from socialos.celery import app as celery_app

            celery_app.control.inspect(timeout=1).ping()
            return True
        except Exception:
            # Celery being down doesn't block web traffic — degrade gracefully.
            logger.warning("Readiness: Celery check failed (non-critical)")
            return False
