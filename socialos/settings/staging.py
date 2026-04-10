from .production import *  # noqa: F401, F403
from .base import env_var

# Allow debug in staging for error inspection
DEBUG = env_var("DEBUG", default=False, cast=bool)  # noqa: F405

# Staging-specific Sentry environment tag
SENTRY_ENVIRONMENT = "staging"

# Relax HSTS in staging (don't preload)
SECURE_HSTS_SECONDS = 300
SECURE_HSTS_PRELOAD = False
