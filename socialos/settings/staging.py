"""
SocialOS — Staging Settings
============================
Mirrors production as closely as possible, but with:
- DEBUG allowed for developers to inspect errors.
- Relaxed security headers.
- Same S3/Redis/PG topology as production.
"""

from .production import *  # noqa: F401, F403

# Allow debug in staging for error inspection
DEBUG = config("DEBUG", default=False, cast=bool)  # noqa: F405

# Staging-specific Sentry environment tag
SENTRY_ENVIRONMENT = "staging"

# Relax HSTS in staging (don't preload)
SECURE_HSTS_SECONDS = 300
SECURE_HSTS_PRELOAD = False
