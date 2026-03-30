"""
SocialOS — Base Settings
========================
Shared across all environments. Never used directly; always imported by an
environment-specific module (development / staging / production).

Configuration is read from environment variables using python-decouple,
which reads from a .env file or the process environment.
"""
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# BASE_DIR → project root (the directory containing manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY: str = config("DJANGO_SECRET_KEY")
DEBUG: bool = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS: list[str] = config("ALLOWED_HOSTS", default="", cast=Csv())

# ---------------------------------------------------------------------------
# Application Definition — django-tenants schema-per-tenant architecture
# ---------------------------------------------------------------------------
# SHARED_APPS: tables created only in the public schema (users, orgs, tokens).
# django_tenants must be first.
SHARED_APPS = [
    "django_tenants",

    # Django built-ins (public schema)
    "daphne",                          # Must be before django.contrib.staticfiles
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",

    # Third-party (shared)
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
    "channels",
    "django_celery_beat",
    "django_celery_results",
    "axes",
    "storages",

    # Local — public-schema models: users, orgs, memberships, tokens
    "apps.auth_core.apps.AuthCoreConfig",
    "apps.organizations.apps.OrganizationsConfig",
]

# TENANT_APPS: tables replicated into every tenant's private schema.
TENANT_APPS = [
    "django.contrib.contenttypes",   # needed inside each schema

    "apps.social_accounts.apps.SocialAccountsConfig",
    "apps.content.apps.ContentConfig",
    "apps.scheduler.apps.SchedulerConfig",
    "apps.publisher.apps.PublisherConfig",
    "apps.analytics.apps.AnalyticsConfig",
    "apps.inbox.apps.InboxConfig",
    "apps.ai_engine.apps.AIEngineConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.automation.apps.AutomationConfig",
    "apps.audit.apps.AuditConfig",
]

# django-tenants requires the union; deduplicate without losing order.
INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

# django-tenants configuration
TENANT_MODEL = "organizations.Organization"
TENANT_DOMAIN_MODEL = "organizations.Domain"
DATABASE_ROUTERS = ["django_tenants.routers.TenantSyncRouter"]
TENANT_BASE_DOMAIN: str = config("TENANT_BASE_DOMAIN", default="localhost")

# URL conf served when the request resolves to the public schema (admin, auth,
# OpenAPI docs).  Tenant schemas use ROOT_URLCONF (socialos.urls).
PUBLIC_SCHEMA_URLCONF = "socialos.urls"

# ---------------------------------------------------------------------------
# Middleware
# Order matters:
#   1. Security / WhiteNoise / CORS must be first.
#   2. Axes must come after AuthenticationMiddleware.
#   3. TenantIsolationMiddleware runs last (after request.user is populated).
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    # django-tenants: must be first — sets the DB schema for every request.
    "django_tenants.middleware.main.TenantMainMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",          # Serve static files
    "corsheaders.middleware.CorsMiddleware",               # CORS headers
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",                      # Brute-force protection
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "socialos.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# ASGI / WSGI
# ---------------------------------------------------------------------------
ASGI_APPLICATION = "socialos.asgi.application"
WSGI_APPLICATION = "socialos.wsgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL 16
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        # django-tenants requires its own backend wrapper (wraps psycopg2).
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": config("DB_NAME", default="socialos"),
        "USER": config("DB_USER", default="socialos"),
        "PASSWORD": config("DB_PASSWORD", default="socialos"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        # Persistent connections — avoids TCP handshake overhead.
        # Set to 0 in PgBouncer (transaction-mode) environments.
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 10,
            # Prevent accidental full-table scans from lingering long
            "options": "-c statement_timeout=30000",  # 30 s
        },
        "TEST": {
            "NAME": config("TEST_DB_NAME", default="test_socialos"),
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "auth_core.User"

# ---------------------------------------------------------------------------
# Authentication Backends
# axes.backends.AxesStandaloneBackend must be FIRST so it can reject locked accounts
# before Django's backend even tries to authenticate.
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ---------------------------------------------------------------------------
# Password Validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Caching — Redis
# DB 1 reserved for Django cache (DB 0 = Celery broker, DB 2 = Channels)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_CACHE_URL", default="redis://localhost:6379/1"),
        "KEY_PREFIX": "socialos",
        "TIMEOUT": 300,  # 5 minutes default TTL
        "OPTIONS": {
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
            "retry_on_timeout": True,
            "max_connections": 50,
        },
    }
}

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 86400 * 7   # 7 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# Django Channels — WebSocket layer (Redis DB 2)
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config("REDIS_CHANNEL_URL", default="redis://localhost:6379/2")],
            "capacity": 1500,     # Max messages in-flight per channel group
            "expiry": 10,         # Message TTL (seconds)
        },
    }
}

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "utils.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "apps.auth_core.throttling.OrgPlanThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
    },
    "EXCEPTION_HANDLER": "utils.exceptions.custom_exception_handler",
    # Only JSON responses — no browsable API in production.
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",   # Media uploads
        "rest_framework.parsers.FormParser",
    ],
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",
    "DATE_FORMAT": "%Y-%m-%d",
}

# ---------------------------------------------------------------------------
# JWT — Simple JWT (RS256 in production, HS256 in development)
# RS256 allows public-key verification (e.g., by edge proxies) without the
# private key being distributed.
# ---------------------------------------------------------------------------
SIMPLE_JWT: dict = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,

    # RS256 — overridden to HS256 in development.py
    "ALGORITHM": "RS256",
    "SIGNING_KEY": config("JWT_PRIVATE_KEY", default="").replace("\\n", "\n"),
    "VERIFYING_KEY": config("JWT_PUBLIC_KEY", default="").replace("\\n", "\n"),

    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",

    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",

    # Custom serializer that embeds org + role in the token payload.
    "TOKEN_OBTAIN_SERIALIZER": "apps.auth_core.serializers.CustomTokenObtainSerializer",
    "TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSerializer",

    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",

    "JTI_CLAIM": "jti",
}

# ---------------------------------------------------------------------------
# drf-spectacular (OpenAPI / Swagger)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "SocialOS API",
    "DESCRIPTION": (
        "Production-grade social media management platform API. "
        "Supports scheduling, publishing, analytics, inbox, and AI features "
        "across Facebook, Instagram, Twitter/X, and LinkedIn."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1/",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
    },
    "SECURITY": [{"Bearer": []}],
    "PREPROCESSING_HOOKS": [],
}

# ---------------------------------------------------------------------------
# CORS — django-cors-headers
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS: list[str] = config(
    "CORS_ALLOWED_ORIGINS",
    default=config("FRONTEND_URL", default="http://localhost:3000"),
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-org-slug",     # Optional: tenant hint from frontend
]

# ---------------------------------------------------------------------------
# django-axes — Brute Force Protection
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = 5           # Lock after 5 failed login attempts
AXES_COOLOFF_TIME = timedelta(hours=1)
AXES_RESET_ON_SUCCESS = True     # Unlock on successful login
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_USERNAME_FORM_FIELD = "email"
AXES_ENABLE_ADMIN = True

# ---------------------------------------------------------------------------
# Celery — Task Queue
# ---------------------------------------------------------------------------
CELERY_BROKER_URL: str = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"   # Persisted results via django-celery-results
CELERY_CACHE_BACKEND = "default"

# Serialization
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# Time
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True

# Reliability
CELERY_TASK_ACKS_LATE = True            # Acknowledge after completion, not on receipt
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1       # Fetch one task at a time (fair distribution)
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500     # Recycle workers to prevent memory leaks

# Timeouts
CELERY_TASK_TIME_LIMIT = 30 * 60        # 30-minute hard kill
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60   # 25-minute soft limit (raises SoftTimeLimitExceeded)

# Tracking
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True

# Beat scheduler (periodic tasks stored in DB, editable via admin)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Celery — Queue Routing
# Tasks are routed to dedicated queues so workers can be scaled independently.
# ---------------------------------------------------------------------------
CELERY_TASK_ROUTES = {
    "apps.publisher.tasks.publish_post":             {"queue": "publish"},
    "apps.scheduler.tasks.process_recurring_schedules": {"queue": "scheduler"},
    "apps.analytics.tasks.*":                        {"queue": "analytics"},
    "apps.ai_engine.tasks.*":                        {"queue": "ai"},
    "apps.notifications.tasks.*":                    {"queue": "notifications"},
    "apps.audit.tasks.*":                            {"queue": "audit"},
    "apps.content.tasks.generate_report":            {"queue": "reports"},
}

# Default queue for unrouted tasks
CELERY_TASK_DEFAULT_QUEUE = "default"

# ---------------------------------------------------------------------------
# Celery Results (django-celery-results)
# ---------------------------------------------------------------------------
DJANGO_CELERY_RESULTS_TASK_ID_MAX_LENGTH = 191

# ---------------------------------------------------------------------------
# Static & Media Files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True   # All datetimes are UTC-aware — convert at UI edge only.

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.example.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="SocialOS <noreply@socialos.io>")

# ---------------------------------------------------------------------------
# Security Headers (base values — strengthened in production.py)
# ---------------------------------------------------------------------------
X_FRAME_OPTIONS = "DENY"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# Social OAuth Credentials
# ---------------------------------------------------------------------------
FACEBOOK_APP_ID: str = config("FACEBOOK_APP_ID", default="")
FACEBOOK_APP_SECRET: str = config("FACEBOOK_APP_SECRET", default="")
FACEBOOK_CALLBACK_URL: str = config("FACEBOOK_CALLBACK_URL", default="")

TWITTER_CLIENT_ID: str = config("TWITTER_CLIENT_ID", default="")
TWITTER_CLIENT_SECRET: str = config("TWITTER_CLIENT_SECRET", default="")
TWITTER_CALLBACK_URL: str = config("TWITTER_CALLBACK_URL", default="")

LINKEDIN_CLIENT_ID: str = config("LINKEDIN_CLIENT_ID", default="")
LINKEDIN_CLIENT_SECRET: str = config("LINKEDIN_CLIENT_SECRET", default="")
LINKEDIN_CALLBACK_URL: str = config("LINKEDIN_CALLBACK_URL", default="")

# ---------------------------------------------------------------------------
# Token Encryption (AES-256-GCM for OAuth tokens stored at rest)
# ---------------------------------------------------------------------------
TOKEN_ENCRYPTION_KEY: str = config("TOKEN_ENCRYPTION_KEY", default="")

# ---------------------------------------------------------------------------
# AI Providers
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = config("OPENAI_API_KEY", default="")
ANTHROPIC_API_KEY: str = config("ANTHROPIC_API_KEY", default="")

# ---------------------------------------------------------------------------
# Stripe (Billing)
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY: str = config("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY: str = config("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET: str = config("STRIPE_WEBHOOK_SECRET", default="")

# ---------------------------------------------------------------------------
# Sentry (Error Tracking)
# ---------------------------------------------------------------------------
SENTRY_DSN: str = config("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT: str = config("SENTRY_ENVIRONMENT", default="development")

# ---------------------------------------------------------------------------
# Kafka / Redis Streams Event Bus
# ---------------------------------------------------------------------------
USE_KAFKA: bool = config("USE_KAFKA", default=False, cast=bool)
KAFKA_BOOTSTRAP_SERVERS: str = config("KAFKA_BOOTSTRAP_SERVERS", default="localhost:9092")
KAFKA_SECURITY_PROTOCOL: str = config("KAFKA_SECURITY_PROTOCOL", default="PLAINTEXT")

# ---------------------------------------------------------------------------
# Plan Limits (enforced at request time via OrgPlanThrottle + plan_limits JSON)
# ---------------------------------------------------------------------------
PLAN_LIMITS = {
    "free": {
        "social_accounts": 3,
        "scheduled_posts_per_month": 30,
        "team_members": 1,
        "analytics_history_days": 7,
        "ai_credits_per_month": 10,
        "approval_workflows": False,
        "unified_inbox": "basic",
        "custom_reports": False,
        "api_access": False,
    },
    "pro": {
        "social_accounts": 10,
        "scheduled_posts_per_month": 500,
        "team_members": 3,
        "analytics_history_days": 90,
        "ai_credits_per_month": 200,
        "approval_workflows": True,
        "unified_inbox": "full",
        "custom_reports": False,
        "api_access": False,
    },
    "business": {
        "social_accounts": 25,
        "scheduled_posts_per_month": None,  # Unlimited
        "team_members": 10,
        "analytics_history_days": 365,
        "ai_credits_per_month": 1000,
        "approval_workflows": True,
        "unified_inbox": "full",
        "custom_reports": True,
        "api_access": True,
    },
    "enterprise": {
        "social_accounts": None,            # Unlimited
        "scheduled_posts_per_month": None,
        "team_members": None,
        "analytics_history_days": None,
        "ai_credits_per_month": None,
        "approval_workflows": True,
        "unified_inbox": "full",
        "custom_reports": True,
        "api_access": True,
        "sso": True,
        "sla": "99.9%",
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": (
                "[{asctime}] {levelname} [{name}:{lineno}] "
                "pid={process:d} tid={thread:d} — {message}"
            ),
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",   # Set to DEBUG to log SQL queries
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Application loggers
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "utils": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
