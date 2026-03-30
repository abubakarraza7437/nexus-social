"""
Notifications — Channel Layer Dispatcher
==========================================
Thin wrappers around channel_layer.group_send() for use inside
synchronous Celery tasks.

Usage (from any Celery task or Django signal):
    from apps.notifications.dispatcher import notify_org, notify_user

    notify_org(post.org_id, "post.status_update", {
        "post_id": str(post.id),
        "status":  "published",
    })
"""
import logging
from typing import Any
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def _send(group: str, event_type: str, payload: dict[str, Any]) -> None:
    """
    Synchronously send a message to a channel group.
    async_to_sync bridges the sync Celery context → async Channels layer.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Channel layer not configured — skipping dispatch to %s", group)
        return

    # Channels routes by event["type"] — dots must become underscores.
    message = {"type": event_type.replace(".", "_"), **payload}

    try:
        async_to_sync(channel_layer.group_send)(group, message)
    except Exception:
        logger.exception("Failed to dispatch %s to group %s", event_type, group)


def notify_org(org_id: str | UUID, event_type: str, payload: dict[str, Any]) -> None:
    """Broadcast an event to every connected member of an organisation."""
    _send(f"org_{org_id}", event_type, payload)


def notify_user(user_id: str | UUID, event_type: str, payload: dict[str, Any]) -> None:
    """Send an event to a specific user (all their open tabs/devices)."""
    _send(f"user_{user_id}", event_type, payload)
