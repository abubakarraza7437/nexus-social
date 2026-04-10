from celery import shared_task, current_app
from celery.utils.log import get_task_logger
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.scheduler.models import RecurringSchedule

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="scheduler",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def dispatch_due_posts(self):
    """
    Periodic task (runs every 5 minutes via CELERY_BEAT_SCHEDULE).

    For each active tenant:
      1. Process any RecurringSchedule records whose next_run_at is due.
      2. Enqueue a publish_post task for every PostTarget that is SCHEDULED
         and whose parent Post.scheduled_at is in the past.
    """
    now = timezone.now()
    dispatched = 0
    schedules_fired = 0

    Tenant = get_tenant_model()

    for tenant in Tenant.objects.filter(is_active=True):
        try:
            with schema_context(tenant.schema_name):
                schedules_fired += _process_recurring_schedules(tenant, now)
                dispatched += _dispatch_due_targets(tenant, now)
        except Exception:
            logger.exception(
                "Error processing tenant schema '%s'", tenant.schema_name
            )
            # Continue to the next tenant — one broken schema must not block others.

    logger.info(
        "dispatch_due_posts complete: %d recurring schedules fired, %d targets dispatched",
        schedules_fired,
        dispatched,
    )
    return {"schedules_fired": schedules_fired, "dispatched": dispatched}


def _process_recurring_schedules(tenant, now) -> int:
    """
    Advance all due, active RecurringSchedule records for this tenant.

    Uses select_for_update(skip_locked=True) so that if two Beat workers ever
    run simultaneously, they process different schedules rather than colliding.

    Returns the count of schedules that fired.
    """
    due_schedules = RecurringSchedule.objects.filter(
        is_active=True,
        next_run_at__lte=now,
    ).select_for_update(skip_locked=True)

    fired = 0
    for schedule in due_schedules:
        try:
            schedule.run_count += 1
            schedule.last_run_at = now

            if schedule.is_exhausted:
                schedule.deactivate()
                logger.info(
                    "RecurringSchedule %s exhausted after %d runs — deactivated",
                    schedule.id,
                    schedule.run_count,
                )
            else:
                schedule.refresh_next_run(after=now)
                schedule.save(update_fields=["run_count", "last_run_at", "updated_at"])

            fired += 1
        except Exception:
            logger.exception(
                "Failed to process RecurringSchedule %s for tenant %s",
                schedule.id,
                tenant.schema_name,
            )

    return fired


def _dispatch_due_targets(tenant, now) -> int:
    """
    Enqueue publish_post for every PostTarget that is SCHEDULED and past its
    parent Post.scheduled_at.

    PostTarget is imported lazily — it lives in apps/posts (a separate app
    boundary). This is a read-only FK lookup, permitted by CLAUDE.md §2.
    Cross-app task invocation uses current_app.send_task() to avoid a direct
    function import across app boundaries.

    Uses iterator(chunk_size=200) to avoid loading thousands of rows into RAM.

    Returns the count of targets dispatched.
    """
    from apps.posts.models import PostTarget  # noqa: PLC0415 — read-only FK lookup

    due_targets = PostTarget.objects.filter(
        status=PostTarget.Status.SCHEDULED,
        post__scheduled_at__lte=now,
    ).select_related("post").iterator(chunk_size=200)

    dispatched = 0
    for target in due_targets:
        try:
            current_app.send_task(
                "apps.publisher.tasks.publish_post",
                args=[str(target.pk), tenant.schema_name],
                task_id=f"publish-{target.pk}",
                queue="publish",
            )
            dispatched += 1
        except Exception:
            logger.exception(
                "Failed to enqueue publish task for PostTarget %s", target.pk
            )

    return dispatched
