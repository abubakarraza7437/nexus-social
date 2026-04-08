"""
Publisher · Models
==================
Tracks async publish jobs associated with PostTargets.
One job per PostTarget per attempt cycle.
"""

import uuid
import datetime
from django.db import models
from django.utils import timezone
from apps.posts.models import PostTarget
from apps.organizations.models import Organization


class PublishJob(models.Model):
    """
    Tracks a single Celery task dispatched to publish one PostTarget.

    Lifecycle
    ---------
    PENDING → RUNNING → SUCCESS
                      ↘ FAILED → (retry) → PENDING ...

    One active job (PENDING or RUNNING) is enforced per PostTarget via a
    partial UniqueConstraint. Completed jobs (SUCCESS / FAILED) are kept
    for the audit log; only the active row is constrained.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="publish_jobs",
        help_text="Organization this job belongs to (for RLS).",
    )
    target = models.ForeignKey(
        PostTarget,
        on_delete=models.CASCADE,
        related_name="publish_jobs",
        help_text="The specific platform/account delivery this job serves.",
    )
    task_name = models.CharField(
        max_length=255,
        help_text="Dotted Celery task path, e.g. publisher.tasks.publish_target",
    )
    celery_task_id = models.CharField(
        max_length=191,
        unique=True,
        blank=True,
        help_text="UUID assigned by Celery at dispatch time.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempt_number = models.PositiveSmallIntegerField(
        default=1,
        help_text="Which attempt this job represents (1-indexed).",
    )
    max_attempts = models.PositiveSmallIntegerField(
        default=3,
        help_text="Stop retrying after this many total attempts.",
    )
    retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to re-enqueue after a failure. Null = no retry scheduled.",
    )
    result = models.JSONField(
        default=dict,
        blank=True,
        help_text='Success payload, e.g. {"remote_post_id": "xyz123"}',
    )
    error = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Structured failure info: '
            '{"code": "RATE_LIMITED", "message": "...", "traceback": "...", "at": "..."}'
        ),
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "publish_jobs"
        constraints = [
            # One active job per target at a time
            models.UniqueConstraint(
                fields=["target"],
                condition=models.Q(status__in=["pending", "running"]),
                name="one_active_job_per_target",
            ),
        ]
        indexes = [
            models.Index(fields=["org", "status"], name="publish_jobs_org_status_idx"),
            models.Index(fields=["org", "target", "status"], name="publish_jobs_org_target_idx"),
            models.Index(fields=["target", "status"], name="publish_jobs_target_status_idx"),
            models.Index(fields=["status", "retry_at"], name="publish_jobs_status_retry_idx"),
            models.Index(fields=["created_at"], name="publish_jobs_created_at_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"PublishJob {self.celery_task_id} "
            f"— target={self.target_id} "
            f"attempt={self.attempt_number}/{self.max_attempts} "
            f"[{self.status}]"
        )

    def mark_running(self) -> None:
        """Signal that the Celery worker has picked up this job."""
        self.status = self.Status.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at", "updated_at"])

    def mark_success(self, result: dict | None = None) -> None:
        """
        Record a successful publish.

        Emits a 'publish_job.succeeded' event for the posts app to handle
        (bounded context — we don't write to PostTarget directly).
        """
        from apps.publisher.events import emit_job_succeeded

        self.status = self.Status.SUCCESS
        self.result = result or {}
        self.error = {}
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "result", "error", "completed_at", "updated_at"])

        # Emit event for posts app to update PostTarget
        remote_id = self.result.get("remote_post_id", "")
        emit_job_succeeded(
            org_id=str(self.org_id),
            target_id=str(self.target_id),
            remote_post_id=remote_id,
        )

    def mark_failed(
        self,
        code: str,
        message: str,
        traceback: str = "",
        schedule_retry: bool = True,
    ) -> None:
        """
        Record a failure with structured error info.

        If attempts remain and schedule_retry=True, computes exponential
        backoff and sets retry_at for the scheduler to re-enqueue.
        Otherwise emits a 'publish_job.failed' event for the posts app.
        """
        from apps.publisher.events import emit_job_failed

        self.status = self.Status.FAILED
        self.error = {
            "code": code,
            "message": message,
            "traceback": traceback,
            "at": timezone.now().isoformat(),
        }
        self.completed_at = timezone.now()

        if schedule_retry and self.can_retry:
            backoff_seconds = 60 * (2 ** (self.attempt_number - 1))  # 1m -> 2m -> 4m
            self.retry_at = timezone.now() + datetime.timedelta(seconds=backoff_seconds)
        else:
            self.retry_at = None

        self.save(update_fields=["status", "error", "completed_at", "retry_at", "updated_at"])

        # Emit event only if no more retries — posts app will mark PostTarget as failed
        if not (schedule_retry and self.can_retry):
            emit_job_failed(
                org_id=str(self.org_id),
                target_id=str(self.target_id),
                code=code,
                message=message,
            )

    @property
    def can_retry(self) -> bool:
        """True if another attempt is still allowed."""
        return self.attempt_number < self.max_attempts

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock seconds between worker pickup and completion."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
