"""
API v1 — URL Dispatcher
========================
Canonical entry point for all v1 traffic.  Each app owns its own URL module;
this file is the single fan-out point.

v1 is the current stable release.  It will eventually enter a deprecation
window before being sunset.  When that happens every v1 view will gain a
``DeprecationWarningMixin`` so existing clients receive advance notice via
``Deprecation`` / ``Sunset`` HTTP headers.

Mounted at ``/api/v1/`` in ``socialos/urls.py``.
"""
from django.urls import include, path

urlpatterns = [
    # Authentication — signup, login, refresh, logout, password reset, email verification
    path("auth/", include("apps.auth_core.urls", namespace="auth")),

    # Organisation management — CRUD, members, invitations, join requests
    path("orgs/", include("apps.organizations.urls", namespace="organizations")),

    # Connected social accounts — connect, disconnect, OAuth token refresh
    path("social-accounts/", include("apps.social_accounts.urls", namespace="social_accounts")),

    # Content — posts, drafts, campaigns, media, templates
    path("posts/", include("apps.content.urls", namespace="content")),

    # Analytics — post metrics, audience insights, reports
    path("analytics/", include("apps.analytics.urls", namespace="analytics")),

    # Unified inbox — conversations, messages, replies, assignments
    path("inbox/", include("apps.inbox.urls", namespace="inbox")),

    # AI engine — caption generation, hashtags, rewrites, best-times
    path("ai/", include("apps.ai_engine.urls", namespace="ai_engine")),

    # Automation rules
    path("automation/", include("apps.automation.urls", namespace="automation")),
]
