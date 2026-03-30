"""
Celery application configuration for SocialOS.

Queue topology (priority order):
  publish (10) → scheduler (8) → ai (6) → analytics (5)
  → notifications (4) → reports (2) → audit (1)
"""
import os

from celery import Celery
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# Default to development; overridden by DJANGO_SETTINGS_MODULE env var in containers.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socialos.settings.development")

app = Celery("socialos")

# Load configuration from Django settings, using the CELERY_ namespace.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Automatically discover tasks in all INSTALLED_APPS.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:  # pragma: no cover
    """Health-check task — prints request info."""
    logger.info("Request: %r", self.request)
