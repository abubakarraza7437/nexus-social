from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="audit",
    max_retries=2,
    acks_late=True,
    ignore_result=True,
)
def log_request_task(
    self,
    user_id: str | None,
    org_id: str | None,
    method: str,
    path: str,
    status_code: int,
    ip_address: str,
) -> None:
    """
    Persist an AuditLog entry for a single HTTP request.

    Called by AuditMiddleware after every mutating request (POST/PUT/PATCH/DELETE).
    Runs in the 'audit' queue (lowest priority) so it never competes with
    publishing or scheduling work.
    """
    from django.contrib.auth import get_user_model
    from apps.audit.models import AuditLog

    User = get_user_model()

    user = None
    if user_id:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            pass

    try:
        AuditLog.objects.create(
            user=user,
            org_id=org_id or "",
            method=method,
            path=path,
            status_code=status_code,
            ip_address=ip_address or None,
        )
    except Exception as exc:
        logger.exception(
            "Failed to write AuditLog entry: method=%s path=%s", method, path
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    queue="audit",
    max_retries=2,
    acks_late=True,
    ignore_result=True,
)
def log_model_event_task(self, **kwargs) -> None:
    """
    Persist a model-level audit event (create/update/delete on key models).

    Payload keys (all optional):
        model_label  — e.g. "posts.Post"
        object_id    — string PK of the affected object
        action       — "created" | "updated" | "deleted"
        actor_id     — user who triggered the change
        org_id       — tenant UUID
        changes      — dict of field-level diffs {"field": [old, new]}
    """
    logger.debug("log_model_event_task received: %s", kwargs)
    # Extend with an AuditModelEvent model when the model-event audit feature lands.
