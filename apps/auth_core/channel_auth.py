"""
Auth Core — JWT Authentication Middleware for Django Channels
==============================================================
Authenticates WebSocket connections using a JWT passed as a query parameter:
  ws://host/ws/events/?token=<access_token>

Sets scope["user"] so Channels consumers can access the authenticated user
the same way Django views use request.user.
"""

from typing import Any
from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


@database_sync_to_async
def _get_user_from_token(token_str: str) -> Any:
    """Validate the JWT and return the associated User, or AnonymousUser."""
    try:
        token = AccessToken(token_str)
        user_id = token["user_id"]
        return User.objects.get(id=user_id, is_active=True)
    except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JWTAuthMiddleware:
    """
    ASGI middleware that reads ?token= from the WebSocket query string
    and populates scope["user"].
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive, send) -> None:
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token_list = params.get("token", [])

        if token_list:
            scope["user"] = await _get_user_from_token(token_list[0])
        else:
            scope["user"] = AnonymousUser()

        return await self.app(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """Wrap the Channels auth stack with JWT middleware."""
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
