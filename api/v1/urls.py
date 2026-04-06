"""
API v1 — Central Router
========================
Pure routing — no views or serializers live here.
Each app owns its own v1/ subpackage with views, serializers, and urls.

Mounted at /api/v1/ in socialos/urls.py.
"""
from django.urls import include, path

urlpatterns = [
    # Implemented apps — versioned subpackages
    path("auth/", include("apps.auth_core.v1.urls", namespace="auth")),
    path("orgs/", include("apps.organizations.v1.urls", namespace="organizations")),

    # Stub apps — single urls.py until the app is fully implemented
    path("social-accounts/", include("apps.social_accounts.urls", namespace="social_accounts")),
    path("posts/", include("apps.content.urls", namespace="content")),
    path("analytics/", include("apps.analytics.urls", namespace="analytics")),
    path("inbox/", include("apps.inbox.urls", namespace="inbox")),
    path("ai/", include("apps.ai_engine.urls", namespace="ai_engine")),
    path("automation/", include("apps.automation.urls", namespace="automation")),
]
