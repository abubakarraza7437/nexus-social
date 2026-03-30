"""
Inbox — WebSocket Consumer
============================
InboxConsumer handles the ws/inbox/ endpoint.
Delivers real-time comment and DM events to authenticated users.
"""
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class InboxConsumer(AsyncJsonWebsocketConsumer):
    """Real-time inbox stream — comments, DMs, assignment updates."""

    async def connect(self) -> None:
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.user_group = f"inbox_user_{user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if getattr(self, "user_group", None):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def inbox_message(self, event: dict) -> None:
        """New inbox message / comment received."""
        await self.send_json({
            "type": "inbox.message",
            "conversationId": event["conversation_id"],
            "message":        event["message"],
        })
