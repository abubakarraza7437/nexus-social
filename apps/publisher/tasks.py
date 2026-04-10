from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction, IntegrityError
from django_tenants.utils import schema_context

from apps.posts.models import PostTarget
from apps.publisher.models import PublishJob
from apps.publisher.platforms.mock import MockPublisher
from apps.publisher.schemas import PublishSuccessPayload

logger = get_task_logger(__name__)


class RetryablePublishError(Exception):
    """Raised on a recoverable publish failure to trigger Celery's retry mechanism."""


@shared_task(
    bind=True,
    queue='publish',
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
        attempt = self.request.retries + 1          # 1-indexed current attempt
        is_final = self.request.retries >= self.max_retries

        # 1. Fetch PostTarget
        try:
            post_target = PostTarget.objects.select_related('post').get(pk=post_target_id)
        except PostTarget.DoesNotExist:
            logger.error("PostTarget not found", extra={"post_target_id": post_target_id})
            return

        # 2. Idempotency check — skip if already published
        if post_target.status == PostTarget.Status.PUBLISHED:
            logger.info(
                "PostTarget already published, skipping",
                extra={"post_target_id": post_target_id, "remote_post_id": post_target.remote_post_id},
            )
            return

        # 3. Acquire lock via PublishJob (DB-level constraint enforces one active job).
        # Append retry count so each attempt gets a unique celery_task_id.
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
                "Active PublishJob already exists for this target",
                extra={"post_target_id": post_target_id},
            )
            return

        # 4. Transition to PUBLISHING
        job.mark_running()
        post_target.status = PostTarget.Status.PUBLISHING
        post_target.save(update_fields=["status", "updated_at"])
        post_target.post.sync_status()

        # 5. Call publisher
        publisher = MockPublisher()
        result = publisher.publish(post_target)

        # 6. Handle result
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
