"""
SocialOS — WSGI Configuration
================================
Used by Gunicorn for HTTP-only deployments.
For WebSocket support, use the ASGI entry point (asgi.py) with Daphne or Uvicorn.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socialos.settings.production")

application = get_wsgi_application()
