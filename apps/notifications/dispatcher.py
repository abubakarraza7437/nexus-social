"""
Notifications — Channel Layer Dispatcher
==========================================
Thin wrappers around channel_layer.group_send() for use inside
synchronous Celery tasks.

Usage (from any Celery task or Django signal):
    from apps.notifications.dispatcher import notify_org, notify_user
    from apps.notifications.schemas import PostStatusUpdateEvent

    notify_org(post.org_id, PostStatusUpdateEvent(
        post_id=str(post.id),
        status="published",
    ))
"""
import logging
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.notifications.schemas import ChannelEvent

logger = logging.getLogger(__name__)


def _send(group: str, event: ChannelEvent) -> None:
    """
    Synchronously send a typed event to a channel group.
    async_to_sync bridges the sync Celery context → async Channels layer.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Channel layer not configured — skipping dispatch to %s", group)
        return

    try:
        async_to_sync(channel_layer.group_send)(group, event.to_channel_message())
    except Exception:
        logger.exception(
            "Failed to dispatch %s to group %s",
            event.type,
            group,
        )


def notify_org(org_id: str | UUID, event: ChannelEvent) -> None:
    """Broadcast a typed event to every connected member of an organisation."""
    _send(f"org_{org_id}", event)


def notify_user(user_id: str | UUID, event: ChannelEvent) -> None:
    """Send a typed event to a specific user (all their open tabs/devices)."""
    _send(f"user_{user_id}", event)
