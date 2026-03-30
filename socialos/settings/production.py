"""
SocialOS — Production Settings
================================
- DEBUG is always False.
- RS256 JWT with private/public key pair.
- AWS S3 + CloudFront for media.
- Strict security headers and HTTPS enforcement.
- Sentry error tracking enabled.
"""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from .base import *  # noqa: F401, F403
from .base import SENTRY_DSN, SENTRY_ENVIRONMENT, config

# ---------------------------------------------------------------------------
# Core — Debug MUST be False in production
# ---------------------------------------------------------------------------
DEBUG = False

# ---------------------------------------------------------------------------
# Security — HTTPS Enforcement
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Strict"

# ---------------------------------------------------------------------------
# AWS S3 + CloudFront — Media Storage
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None  # Use bucket policy / ACLs disabled
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",
}
# Public media (images); use signed URLs for private
AWS_QUERYSTRING_AUTH = False
AWS_S3_CUSTOM_DOMAIN = config("AWS_CLOUDFRONT_DOMAIN", default="")

# Store media files on S3
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME,
            "custom_domain": AWS_S3_CUSTOM_DOMAIN or None,
            "file_overwrite": False,
        },
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = (
    f"https://{AWS_S3_CUSTOM_DOMAIN}/"
    if AWS_S3_CUSTOM_DOMAIN
    else f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"
)

# ---------------------------------------------------------------------------
# JWT — RS256 with proper key pair
# ---------------------------------------------------------------------------
_jwt_private_key = config("JWT_PRIVATE_KEY").replace("\\n", "\n")
_jwt_public_key = config("JWT_PUBLIC_KEY").replace("\\n", "\n")

SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "ALGORITHM": "RS256",
    "SIGNING_KEY": _jwt_private_key,
    "VERIFYING_KEY": _jwt_public_key,
}

# ---------------------------------------------------------------------------
# Email — Production SMTP
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---------------------------------------------------------------------------
# Sentry — Error & Performance Tracking
# ---------------------------------------------------------------------------
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(monitor_beat_tasks=True),
            RedisIntegration(),
        ],
        # Send 10% of transactions for performance monitoring
        traces_sample_rate=0.1,
        # PII is scrubbed by default — do not enable send_default_pii
        send_default_pii=False,
        release=config("APP_VERSION", default="unknown"),
    )

# ---------------------------------------------------------------------------
# Logging — structured for log aggregation (Datadog, CloudWatch, etc.)
# ---------------------------------------------------------------------------
LOGGING["formatters"]["verbose"]["format"] = (  # noqa: F405
    '{"time": "{asctime}", "level": "{levelname}", "logger": "{name}", ' '"line": {lineno}, "message": "{message}"}'
)
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "INFO"  # noqa: F405
