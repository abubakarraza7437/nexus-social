"""
SocialOS — Development Settings
================================
- DEBUG is on; all origins are allowed.
- JWT uses HS256 (no key-pair needed for local dev).
- Emails print to console.
- Django Silk + Extensions enabled for profiling.
- Celery runs eagerly so tasks execute synchronously in tests when configured.
"""
from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
DEBUG = True

ALLOWED_HOSTS = ["*"]

# ---------------------------------------------------------------------------
# JWT — HS256 for local development (no need to generate RSA key pair)
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,  # noqa: F405
    "VERIFYING_KEY": None,
    # Longer lifetime for convenience during development
    "ACCESS_TOKEN_LIFETIME": __import__("datetime").timedelta(hours=1),
}

# ---------------------------------------------------------------------------
# Database — local PostgreSQL (overridable via .env)
# ---------------------------------------------------------------------------
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405  # Disable persistent conns in dev

# ---------------------------------------------------------------------------
# Email — Use SMTP backend from .env (falls back to console for dev convenience)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = config(  # noqa: F405
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

# ---------------------------------------------------------------------------
# CORS — Accept all origins in development
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Internal IPs — for Django Debug Toolbar / Silk
# ---------------------------------------------------------------------------
INTERNAL_IPS = ["127.0.0.1", "::1", "0.0.0.0"]

# ---------------------------------------------------------------------------
# Dev-only Installed Apps
# ---------------------------------------------------------------------------
INSTALLED_APPS += [  # noqa: F405
    "django_extensions",
    "silk",
]

# ---------------------------------------------------------------------------
# Silk — Request/SQL profiling (accessible at /silk/)
# ---------------------------------------------------------------------------
MIDDLEWARE = [  # noqa: F405
    "silk.middleware.SilkyMiddleware",
    *MIDDLEWARE,  # noqa: F405
]

SILKY_PYTHON_PROFILER = True
SILKY_META = True
SILKY_INTERCEPT_PERCENT = 100   # Profile all requests in dev

# ---------------------------------------------------------------------------
# DRF — Enable Browsable API in development
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# ---------------------------------------------------------------------------
# Celery — always-eager option (useful in unit tests)
# Set CELERY_TASK_ALWAYS_EAGER=True in .env to run tasks synchronously.
# ---------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)  # noqa: F405

# ---------------------------------------------------------------------------
# Caching — local Redis or in-memory fallback
# ---------------------------------------------------------------------------
# Uncomment to use in-memory cache (no Redis required):
# CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ---------------------------------------------------------------------------
# Logging — verbose SQL + app logs in development
# ---------------------------------------------------------------------------
LOGGING["loggers"]["django.db.backends"]["level"] = "DEBUG"  # noqa: F405
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
