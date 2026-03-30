"""
SocialOS — API v1 URL Dispatcher
==================================
Each app owns its URL module; this file is the single import point.
"""

from django.urls import include, path

urlpatterns = [
    # Auth (register, login, refresh, logout, MFA, OAuth)
    path("auth/", include("apps.auth_core.urls", namespace="auth")),
    # Organization management
    path(
        "organizations/",
        include("apps.organizations.urls", namespace="organizations"),
    ),
    # Connected social accounts (connect, disconnect, token refresh)
    path(
        "social-accounts/",
        include("apps.social_accounts.urls", namespace="social_accounts"),
    ),
    # Content — posts, drafts, campaigns, media, templates
    path("posts/", include("apps.content.urls", namespace="content")),
    # Analytics — overview, post metrics, audience insights, reports
    path("analytics/", include("apps.analytics.urls", namespace="analytics")),
    # Unified inbox — conversations, messages, replies, assignments
    path("inbox/", include("apps.inbox.urls", namespace="inbox")),
    # AI engine — caption, hashtags, rewrite, best-times
    path("ai/", include("apps.ai_engine.urls", namespace="ai_engine")),
    # Automation rules
    path(
        "automation/",
        include("apps.automation.urls", namespace="automation"),
    ),
]
