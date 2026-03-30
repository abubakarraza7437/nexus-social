"""
SocialOS — Django Channels WebSocket URL Routing
==================================================
These patterns are consumed by the ProtocolTypeRouter in asgi.py.
"""
from django.urls import re_path

from apps.inbox.consumers import InboxConsumer
from apps.notifications.consumers import EventConsumer

websocket_urlpatterns = [
    # Real-time post status updates, publish results, team notifications
    re_path(r"^ws/events/$", EventConsumer.as_asgi()),

    # Unified inbox — live message/comment delivery
    re_path(r"^ws/inbox/$", InboxConsumer.as_asgi()),
]
