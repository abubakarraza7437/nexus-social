import logging

from django.db import connection
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


class HealthView(View):

    def get(self, request, *args, **kwargs) -> JsonResponse:
        return JsonResponse({"status": "ok"}, status=200)


class ReadinessView(View):

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
            status=status_code)

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
