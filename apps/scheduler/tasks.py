# apps/scheduler/tasks.py

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.organizations.models import Organization
from apps.posts.models import PostTarget
from apps.publisher.tasks import publish_post

logger = get_task_logger(__name__)


@shared_task(queue='scheduler')
def dispatch_due_posts():

    now = timezone.now()
    dispatched = 0

    for org in Organization.objects.filter(is_active=True):
        with schema_context(org.schema_name):
            due_targets = PostTarget.objects.filter(
                status=PostTarget.Status.SCHEDULED,
                post__scheduled_at__lte=now,
            ).select_related('post')

            for target in due_targets:
                publish_post.apply_async(
                    args=[str(target.pk), org.schema_name],
                    task_id=f"publish-{target.pk}",
                )
                dispatched += 1

    logger.info(f"Dispatched {dispatched} posts for publishing")
    return dispatched
