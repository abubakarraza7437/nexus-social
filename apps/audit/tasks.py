"""Audit — Celery tasks (stubs — models implemented in the audit feature section)."""
from celery import shared_task


@shared_task(queue="audit", ignore_result=True)
def log_request_task(**kwargs) -> None:
    """Record an HTTP request audit entry. Full implementation in audit feature section."""
    pass


@shared_task(queue="audit", ignore_result=True)
def log_model_event_task(**kwargs) -> None:
    """Record a model-level audit event. Full implementation in audit feature section."""
    pass
