import uuid
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Immutable record of every state-changing API request.

    Written asynchronously by apps.audit.tasks.log_request_task so it never
    blocks the response path. Fields are nullable where the data may not be
    available (e.g. unauthenticated requests have no user_id).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    # org_id stored as a plain CharField so the record survives org deletion.
    org_id = models.CharField(max_length=36, blank=True, db_index=True)

    method = models.CharField(max_length=10)
    path = models.CharField(max_length=2048)
    status_code = models.PositiveSmallIntegerField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["org_id", "created_at"], name="audit_org_created_idx"),
            models.Index(fields=["user", "created_at"], name="audit_user_created_idx"),
            models.Index(fields=["status_code", "created_at"], name="audit_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.method}] {self.path} → {self.status_code} ({self.created_at})"
