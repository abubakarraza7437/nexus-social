"""
Audit — Request Logging Middleware
=====================================
Logs every mutating request (POST/PUT/PATCH/DELETE) to the activity_logs
table asynchronously via a Celery task so it never blocks the response path.
"""
import logging

logger = logging.getLogger(__name__)

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuditMiddleware:
    """
    Queues an audit log entry for every state-changing API request.
    Read-only requests (GET, HEAD, OPTIONS) are skipped.
    """

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method in _MUTATING_METHODS and hasattr(request, "user"):
            self._log_async(request, response)

        return response

    def _log_async(self, request, response) -> None:
        try:
            from apps.audit.tasks import log_request_task

            user = request.user
            org = getattr(request, "org", None)

            log_request_task.apply_async(
                kwargs={
                    "user_id":    str(user.id) if user.is_authenticated else None,
                    "org_id":     str(org.id) if org else None,
                    "method":     request.method,
                    "path":       request.path,
                    "status_code": response.status_code,
                    "ip_address": self._get_client_ip(request),
                },
                queue="audit",
            )
        except Exception:
            # Audit logging must never break the response pipeline.
            logger.exception("Failed to queue audit log entry")

    @staticmethod
    def _get_client_ip(request) -> str:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
