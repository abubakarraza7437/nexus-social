"""
SocialOS — Root URL Configuration
===================================
All API routes live under /api/v1/.
Health/readiness endpoints are at the root for Kubernetes probes.
"""

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from utils.health import HealthView, ReadinessView

urlpatterns = [
    # -----------------------------------------------------------------------
    # Health checks — used by Kubernetes liveness & readiness probes.
    # These must respond without auth and without DB access (liveness).
    # -----------------------------------------------------------------------
    path("health/", HealthView.as_view(), name="health"),
    path("ready/", ReadinessView.as_view(), name="readiness"),
    # -----------------------------------------------------------------------
    # Django Admin
    # -----------------------------------------------------------------------
    path("admin/", admin.site.urls),
    # -----------------------------------------------------------------------
    # API v1
    # -----------------------------------------------------------------------
    path("api/v1/", include("socialos.api_urls")),
    # -----------------------------------------------------------------------
    # OpenAPI Schema + Interactive Docs
    # Disable in production via SPECTACULAR_SETTINGS["SERVE_INCLUDE_SCHEMA"]
    # -----------------------------------------------------------------------
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    path(
        "",
        lambda request: HttpResponse("WELCOME TO SOCIALOS!"),
        name="root",
    ),
]
