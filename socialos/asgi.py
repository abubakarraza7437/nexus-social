import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socialos.settings.development")

# Initialise Django BEFORE importing Channels routing (avoids AppRegistryNotReady).
django_asgi_app = get_asgi_application()

# Import the Celery app after Django is fully set up so that @shared_task tasks
# can be dispatched from Django views with the correct broker configuration.
import socialos.celery  # noqa: F401, E402

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.auth_core.channel_auth import JWTAuthMiddlewareStack  # noqa: E402
from socialos.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        # Standard Django HTTP handling
        "http": django_asgi_app,
        # WebSocket connections
        # AllowedHostsOriginValidator → rejects WS connections from untrusted origins.
        # JWTAuthMiddlewareStack      → authenticates via JWT query param or cookie.
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        ),
    }
)
