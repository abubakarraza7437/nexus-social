from celery import Task, shared_task
from celery.utils.log import get_task_logger
from django.db import transaction, IntegrityError
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.posts.models import PostTarget
from apps.publisher.base import ErrorCode
from apps.publisher.models import PublishJob
from apps.publisher.platforms.mock import MockPublisher
from apps.publisher.schemas import PublishSuccessPayload

logger = get_task_logger(__name__)


class RetryablePublishError(Exception):
    """Raised on a recoverable publish failure to trigger Celery's retry mechanism."""


class PublisherTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if len(args) < 2:
            return

        post_target_id, schema_name = args[0], args[1]

        logger.error(
            "publisher.unexpected_failure",
            extra={
                "post_target_id": post_target_id,
                "task_id": task_id,
                "exc_type": type(exc).__name__,
                "error": str(exc),
            },
        )

        try:
            with schema_context(schema_name):
                job = PublishJob.objects.filter(
                    target_id=post_target_id,
                    status=PublishJob.Status.RUNNING,
                ).first()
                if job is not None:
                    job.mark_failed(
                        code=ErrorCode.UNKNOWN,
                        message=str(exc),
                        schedule_retry=False,
                    )
        except Exception:
            logger.exception(
                "on_failure handler could not mark job failed",
                extra={"post_target_id": post_target_id, "task_id": task_id},
            )


@shared_task(
    bind=True,
    base=PublisherTask,
    queue="publish",
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(RetryablePublishError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=False,
)
def publish_post(self, post_target_id: str, schema_name: str):
    with schema_context(schema_name):
        task_id = f"publish-{post_target_id}"
        attempt = self.request.retries + 1
        is_final = self.request.retries >= self.max_retries

        # 1. Fetch PostTarget.
        try:
            post_target = PostTarget.objects.select_related("post").get(pk=post_target_id)
        except PostTarget.DoesNotExist:
            logger.error("PostTarget not found", extra={"post_target_id": post_target_id})
            return

        # 2. Idempotency guard — skip if already published.
        if post_target.status == PostTarget.Status.PUBLISHED:
            logger.info(
                "PostTarget already published, skipping",
                extra={
                    "post_target_id": post_target_id,
                    "remote_post_id": post_target.remote_post_id,
                },
            )
            return

        # 3. Orphan cleanup — if a previous worker crashed while holding a
        #    RUNNING job, that job was never marked failed. Close it out so
        #    the unique constraint doesn't block this attempt.
        closed = PublishJob.objects.filter(
            target_id=post_target_id,
            status=PublishJob.Status.RUNNING,
        ).update(
            status=PublishJob.Status.FAILED,
            error={
                "code": ErrorCode.UNKNOWN,
                "message": "Orphaned by worker crash — closed by subsequent attempt.",
                "at": timezone.now().isoformat(),
            },
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
        if closed:
            logger.warning(
                "Closed %d orphaned RUNNING job(s) for target %s",
                closed,
                post_target_id,
            )
            # Reset target status so it can be re-processed if it was stuck in PUBLISHING.
            if post_target.status == PostTarget.Status.PUBLISHING:
                post_target.status = PostTarget.Status.SCHEDULED
                post_target.save(update_fields=["status", "updated_at"])

        # 4. Acquire lock via PublishJob (DB-level constraint: one active job per target).
        unique_task_id = f"{self.request.id or task_id}-{self.request.retries}"
        try:
            with transaction.atomic():
                job = PublishJob.objects.create(
                    org_id=post_target.post.organization_id,
                    target=post_target,
                    task_name="apps.publisher.tasks.publish_post",
                    celery_task_id=unique_task_id,
                    attempt_number=attempt,
                    max_attempts=self.max_retries + 1,
                )
        except IntegrityError:
            logger.warning(
                "Active PublishJob already exists for target — another worker is processing it",
                extra={"post_target_id": post_target_id},
            )
            return

        # 5. Transition to PUBLISHING.
        job.mark_running()
        post_target.status = PostTarget.Status.PUBLISHING
        post_target.save(update_fields=["status", "updated_at"])
        post_target.post.sync_status()

        # 6. Resolve the correct publisher from the platform registry.
        publisher = MockPublisher()
        result = publisher.publish(post_target)

        # 7. Handle result.
        if result.ok:
            payload = PublishSuccessPayload(
                remote_post_id=result.remote_id,
                extra=result.extra,
            )
            job.mark_success(payload)
            logger.info(
                "Publish succeeded",
                extra={"post_target_id": post_target_id, "remote_id": result.remote_id},
            )
        else:
            job.mark_failed(
                code=result.error_code,
                message=result.message,
                schedule_retry=not is_final,
            )
            logger.warning(
                "Publish failed",
                extra={
                    "post_target_id": post_target_id,
                    "error_code": result.error_code,
                    "attempt": attempt,
                    "is_final": is_final,
                },
            )
            if not is_final:
                raise RetryablePublishError(result.message)
