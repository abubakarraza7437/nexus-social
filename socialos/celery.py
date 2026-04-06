"""
SocialOS — Celery Application
==============================
Initialises the Celery app, declares the full queue topology, wires
lifecycle signals for observability, and provides two built-in tasks:

  socialos.healthcheck  — round-trip test; returns a JSON result
  socialos.debug_task   — request-echo (dev/troubleshooting only)

Queue topology (highest → lowest priority)
-------------------------------------------
  publish (10) → scheduler (8) → ai (6) → analytics (5)
  → notifications (4) → reports (2) → audit (1) → default (0)

Worker startup
--------------
  celery -A socialos worker -Q publish,scheduler,ai,analytics,notifications,reports,audit,default --loglevel=info

Verify a worker is running
--------------------------
  celery -A socialos inspect ping
  celery -A socialos call socialos.healthcheck
"""

import logging
import os
import socket

import django
from celery import Celery
from celery.signals import worker_init, worker_ready, worker_shutdown
from celery.utils.log import get_task_logger
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)
task_logger = get_task_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socialos.settings.development")

# Must be called before creating the Celery app when CELERY_RESULT_BACKEND is
# "django-db".  Without this, the backend tries to import django_celery_results
# models before Django's app registry is initialised, causing AppRegistryNotReady.
# django.setup() is idempotent — safe to call even if Django is already set up.
django.setup()

app = Celery("socialos")

# Pull all CELERY_* settings from Django settings.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in every INSTALLED_APP.
app.autodiscover_tasks()

# ─────────────────────────────────────────────────────────────────────────────
# Broker reliability
# ─────────────────────────────────────────────────────────────────────────────
# Required in Celery ≥ 5.3 to silence the deprecation warning.
# Celery 6.x will raise an error if this is not set.
app.conf.broker_connection_retry_on_startup = True

# ─────────────────────────────────────────────────────────────────────────────
# Queue topology
# ─────────────────────────────────────────────────────────────────────────────
# Declaring queues explicitly here (rather than relying on lazy creation) has
# two benefits:
#   1. Workers validate queue existence on startup → fail-fast if Redis is down.
#   2. x-max-priority enables per-message priority within a queue (RabbitMQ /
#      Redis Streams).  Redis pub/sub ignores this header but it is harmless.
#
# Each queue uses a dedicated routing-key so CELERY_TASK_ROUTES can target them
# without wildcard matching.

_default_exchange = Exchange("default", type="direct")
_task_exchange = Exchange("tasks", type="direct")

app.conf.task_queues = (
    Queue(
        "publish",
        _task_exchange,
        routing_key="publish",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "scheduler",
        _task_exchange,
        routing_key="scheduler",
        queue_arguments={"x-max-priority": 8},
    ),
    Queue(
        "ai",
        _task_exchange,
        routing_key="ai",
        queue_arguments={"x-max-priority": 6},
    ),
    Queue(
        "analytics",
        _task_exchange,
        routing_key="analytics",
        queue_arguments={"x-max-priority": 5},
    ),
    Queue(
        "notifications",
        _task_exchange,
        routing_key="notifications",
        queue_arguments={"x-max-priority": 4},
    ),
    Queue(
        "reports",
        _task_exchange,
        routing_key="reports",
        queue_arguments={"x-max-priority": 2},
    ),
    Queue(
        "audit",
        _task_exchange,
        routing_key="audit",
        queue_arguments={"x-max-priority": 1},
    ),
    Queue(
        "default",
        _default_exchange,
        routing_key="default",
        queue_arguments={"x-max-priority": 0},
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Worker lifecycle signals
# ─────────────────────────────────────────────────────────────────────────────


@worker_init.connect
def on_worker_init(sender, **kwargs) -> None:
    """
    Fired when the worker process boots, before consuming tasks.
    Useful for verifying broker connectivity on startup.
    """
    logger.info(
        "[celery:worker_init] hostname=%s pid=%s host=%s",
        getattr(sender, "hostname", "?"),
        os.getpid(),
        socket.gethostname(),
    )


@worker_ready.connect
def on_worker_ready(sender, **kwargs) -> None:
    """
    Fired when the worker has connected to the broker and is ready to consume.
    This is the definitive signal that the worker is operational.
    """
    queue_names = [q.name for q in app.conf.task_queues]
    logger.info(
        "[celery:worker_ready] Worker is READY | hostname=%s | queues=%s | concurrency=%s",
        getattr(sender, "hostname", "?"),
        queue_names,
        getattr(sender, "concurrency", "?"),
    )


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs) -> None:
    """Fired when the worker receives a shutdown signal."""
    logger.info(
        "[celery:worker_shutdown] Worker shutting down | hostname=%s",
        getattr(sender, "hostname", "?"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Built-in tasks
# ─────────────────────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="socialos.healthcheck",
    queue="default",
    ignore_result=False,       # result IS stored — used to verify round-trip
    max_retries=3,
    default_retry_delay=5,
)
def healthcheck_task(self) -> dict:
    """
    Round-trip health-check task.

    Dispatches to the default queue, executes on a worker, and stores its
    result in the result backend (django-db).  Use this to confirm that:
      - the broker (Redis) is reachable
      - a worker is running and consuming the default queue
      - the result backend is writable

    Invoke manually:
        celery -A socialos call socialos.healthcheck

    Or from a Django shell:
        from socialos.celery import healthcheck_task
        result = healthcheck_task.delay()
        print(result.get(timeout=10))
    """
    from django.utils import timezone

    payload = {
        "status": "ok",
        "task_id": self.request.id,
        "worker": self.request.hostname,
        "retries": self.request.retries,
        "timestamp": timezone.now().isoformat(),
        "host": socket.gethostname(),
    }

    task_logger.info(
        "[socialos.healthcheck] OK | task_id=%s worker=%s host=%s timestamp=%s",
        payload["task_id"],
        payload["worker"],
        payload["host"],
        payload["timestamp"],
    )

    return payload


@app.task(bind=True, name="socialos.debug_task", ignore_result=True)
def debug_task(self) -> None:
    """
    Request-echo task for local troubleshooting.
    Prints the full task request context — useful when diagnosing routing or
    serialisation issues.

    Invoke:
        celery -A socialos call socialos.debug_task
    """
    task_logger.debug(
        "[socialos.debug_task] request=%r | hostname=%s | args=%r | kwargs=%r",
        self.request,
        self.request.hostname,
        self.request.args,
        self.request.kwargs,
    )
