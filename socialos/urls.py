"""
SocialOS — Root URL Configuration
===================================
Versioned API traffic is handled by dedicated URL dispatchers:

  /api/v1/  →  api.v1.urls   (stable — current default)
  /api/v2/  →  api.v2.urls   (enhanced payloads, new endpoints)

OpenAPI documentation is served per-version:

  /api/docs/v1/      Swagger UI  — v1 endpoints only
  /api/docs/v2/      Swagger UI  — v2 endpoints only
  /api/redoc/v1/     ReDoc       — v1 endpoints only
  /api/redoc/v2/     ReDoc       — v2 endpoints only
  /api/schema/v1/    Raw schema  — v1 (JSON / YAML)
  /api/schema/v2/    Raw schema  — v2 (JSON / YAML)

Health / readiness endpoints live at the root for Kubernetes probes.
"""
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from utils.health import HealthView, ReadinessView

# ---------------------------------------------------------------------------
# Per-version schema views
# Each view overrides PREPROCESSING_HOOKS to filter endpoints by URL prefix.
# ---------------------------------------------------------------------------
_V1_SCHEMA_SETTINGS = {
    "PREPROCESSING_HOOKS": ["api.schema.filter_v1_endpoints"],
    "TITLE": "SocialOS API — v1",
    "VERSION": "1.0.0",
    "SCHEMA_PATH_PREFIX": r"/api/v1/",
}

_V2_SCHEMA_SETTINGS = {
    "PREPROCESSING_HOOKS": ["api.schema.filter_v2_endpoints"],
    "TITLE": "SocialOS API — v2",
    "VERSION": "2.0.0",
    "SCHEMA_PATH_PREFIX": r"/api/v2/",
}

schema_v1 = SpectacularAPIView.as_view(custom_settings=_V1_SCHEMA_SETTINGS)
schema_v2 = SpectacularAPIView.as_view(custom_settings=_V2_SCHEMA_SETTINGS)

urlpatterns = [
    # -----------------------------------------------------------------------
    # Health checks — Kubernetes liveness & readiness probes.
    # These must respond without auth or DB access (liveness).
    # -----------------------------------------------------------------------
    path("health/", HealthView.as_view(), name="health"),
    path("ready/", ReadinessView.as_view(), name="readiness"),

    # -----------------------------------------------------------------------
    # Django Admin
    # -----------------------------------------------------------------------
    path("admin/", admin.site.urls),

    # -----------------------------------------------------------------------
    # Versioned API
    # -----------------------------------------------------------------------
    path("api/v1/", include("api.v1.urls")),
    path("api/v2/", include("api.v2.urls")),

    # -----------------------------------------------------------------------
    # OpenAPI Schema — per version
    # -----------------------------------------------------------------------
    path("api/schema/v1/", schema_v1, name="schema-v1"),
    path("api/schema/v2/", schema_v2, name="schema-v2"),

    # -----------------------------------------------------------------------
    # Interactive Docs — Swagger UI (per version)
    # -----------------------------------------------------------------------
    path(
        "api/docs/v1/",
        SpectacularSwaggerView.as_view(url_name="schema-v1"),
        name="swagger-ui-v1",
    ),
    path(
        "api/docs/v2/",
        SpectacularSwaggerView.as_view(url_name="schema-v2"),
        name="swagger-ui-v2",
    ),

    # -----------------------------------------------------------------------
    # Interactive Docs — ReDoc (per version)
    # -----------------------------------------------------------------------
    path(
        "api/redoc/v1/",
        SpectacularRedocView.as_view(url_name="schema-v1"),
        name="redoc-v1",
    ),
    path(
        "api/redoc/v2/",
        SpectacularRedocView.as_view(url_name="schema-v2"),
        name="redoc-v2",
    ),

    # -----------------------------------------------------------------------
    # Root
    # -----------------------------------------------------------------------
    path("", lambda request: HttpResponse("WELCOME TO SOCIALOS!"), name="root"),
]
