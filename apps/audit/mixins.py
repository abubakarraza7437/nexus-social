"""
Audit — LoggedModelMixin
==========================
Model mixin that auto-records create/update/delete events.
Add to any model that needs a detailed audit trail.
"""

import logging

logger = logging.getLogger(__name__)


class LoggedModelMixin:
    """
    Mixin for Django models to emit audit events on save() and delete().

    Usage:
        class Post(LoggedModelMixin, models.Model):
            ...
    """

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        super().save(*args, **kwargs)  # type: ignore[misc]
        action = "created" if is_new else "updated"
        self._emit_audit(action)

    def delete(self, *args, **kwargs):
        self._emit_audit("deleted")
        return super().delete(*args, **kwargs)  # type: ignore[misc]

    def _emit_audit(self, action: str) -> None:
        try:
            from apps.audit.tasks import log_model_event_task

            log_model_event_task.apply_async(
                kwargs={
                    "model": self.__class__.__name__,
                    "pk": str(self.pk),  # type: ignore[attr-defined]
                    "action": action,
                },
                queue="audit",
            )
        except Exception:
            logger.exception(
                "Failed to queue model audit event for %s pk=%s",
                self.__class__.__name__,
                getattr(self, "pk", None),
            )
