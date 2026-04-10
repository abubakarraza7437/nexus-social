"""
Notifications — WebSocket Consumer
=====================================
EventConsumer handles the ws/events/ endpoint.

On connect: joins two channel groups —
  org_{org_id}   → org-wide broadcasts (post published, team actions)
  user_{user_id} → personal notifications

Celery workers push events via notify_org() / notify_user() in dispatcher.py.
"""
import logging
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.notifications.schemas import NotificationEvent, PostStatusUpdateEvent

logger = logging.getLogger(__name__)


class EventConsumer(AsyncJsonWebsocketConsumer):
    """
    Real-time event stream for a single authenticated user.
    Carries: post status updates, publish results, team notifications.
    """

    async def connect(self) -> None:
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        org_id = self.scope.get("session", {}).get("org_id")
        if not org_id:
            # Try to read org from the JWT claim attached by JWTAuthMiddleware
            token_data = getattr(user, "_jwt_claims", {})
            org_id = token_data.get("org")

        self.org_group = f"org_{org_id}" if org_id else None
        self.user_group = f"user_{user.id}"

        if self.org_group:
            await self.channel_layer.group_add(self.org_group, self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

        logger.debug("WS connected: user=%s org_group=%s", user.id, self.org_group)

    async def disconnect(self, close_code: int) -> None:
        if getattr(self, "org_group", None):
            await self.channel_layer.group_discard(self.org_group, self.channel_name)
        if getattr(self, "user_group", None):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    # ------------------------------------------------------------------
    # Channel layer message handlers
    # Method name = event["type"] with "." replaced by "_"
    # ------------------------------------------------------------------

    async def post_status_update(self, event: dict[str, Any]) -> None:
        """Fired by publisher worker when a post is published or fails."""
        payload = PostStatusUpdateEvent.model_validate(event)
        await self.send_json({
            "type": "post.status",
            "postId": payload.post_id,
            "status": payload.status,
        })

    async def notification(self, event: dict[str, Any]) -> None:
        """Generic notification message (approval requests, token expiry, etc.)."""
        payload = NotificationEvent.model_validate(event)
        await self.send_json({
            "type": "notification",
            "title": payload.title,
            "body":  payload.body,
            "data":  payload.data,
        })
