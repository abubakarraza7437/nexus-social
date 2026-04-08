"""
Notifications · Pydantic schemas
=================================
Typed event payloads for the Django Channels layer.

Every event must subclass ChannelEvent. The `type` field drives routing:
Django Channels calls the consumer method whose name matches
event["type"] with "." replaced by "_".

Usage (dispatcher side):
    notify_org(org_id, PostStatusUpdateEvent(post_id=str(post.id), status="published"))

Usage (consumer side):
    async def post_status_update(self, event: dict) -> None:
        payload = PostStatusUpdateEvent.model_validate(event)
        await self.send_json({"postId": payload.post_id, ...})
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Base                                                                         #
# --------------------------------------------------------------------------- #

class ChannelEvent(BaseModel):
    """
    Base class for all channel layer events.

    Subclasses set `type` as a Literal so the value is fixed and validated.
    Call to_channel_message() to get the dict ready for group_send().
    """

    model_config = ConfigDict(frozen=True)

    type: str

    def to_channel_message(self) -> dict[str, Any]:
        """
        Serialize for channel_layer.group_send().
        Channels routes by event["type"] with "." replaced by "_".
        """
        data = self.model_dump(mode="json")
        data["type"] = data["type"].replace(".", "_")
        return data


# --------------------------------------------------------------------------- #
# Concrete events                                                              #
# --------------------------------------------------------------------------- #

class PostStatusUpdateEvent(ChannelEvent):
    """
    Fired by the publisher worker when a PostTarget is published or fails.
    Routed to: EventConsumer.post_status_update()
    """

    type: Literal["post.status_update"] = "post.status_update"
    post_id: str
    status: str


class NotificationEvent(ChannelEvent):
    """
    Generic user-facing notification (approval requests, token expiry, etc.).
    Routed to: EventConsumer.notification()
    """

    type: Literal["notification"] = "notification"
    title: str = ""
    body: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class InboxMessageEvent(ChannelEvent):
    """
    New inbox message or comment received.
    Routed to: InboxConsumer.inbox_message()
    """

    type: Literal["inbox.message"] = "inbox.message"
    conversation_id: str
    message: dict[str, Any] = Field(
        description="Serialized message payload (id, author, body, created_at, etc.).",
    )
