"""
API v2 — URL Dispatcher
========================
Entry point for all v2 traffic.  Mounted at ``/api/v2/`` in ``socialos/urls.py``.

v2 Strategy
-----------
Only endpoints that have meaningful changes are overridden in v2-specific
modules.  All other endpoints fall back to the same app-level URL modules
used by v1 — so clients get the latest behaviour without duplication.

Override vs. fall-through table
--------------------------------
  Endpoint group    | v2 override?  | Change summary
  ------------------|---------------|--------------------------------------------------
  auth/             | YES           | Login embeds user profile; signup returns user
  orgs/             | YES           | Orgs include member_count; members include invited_by
  social-accounts/  | no            | Unchanged — routes to v1 app module
  posts/            | no            | Unchanged
  analytics/        | no            | Unchanged
  inbox/            | no            | Unchanged
  ai/               | no            | Unchanged
  automation/       | no            | Unchanged

For future v3 work: add a new ``api/v3/`` package and repeat the pattern.
"""
from django.urls import include, path

urlpatterns = [
    # -------------------------------------------------------------------------
    # v2-specific overrides
    # -------------------------------------------------------------------------
    path("auth/", include("api.v2.auth.urls")),
    path("orgs/", include("api.v2.organizations.urls")),

    # -------------------------------------------------------------------------
    # Fall-through to v1 app modules (no changes in v2)
    # -------------------------------------------------------------------------
    path("social-accounts/", include("apps.social_accounts.urls", namespace="v2_social_accounts")),
    path("posts/", include("apps.content.urls", namespace="v2_content")),
    path("analytics/", include("apps.analytics.urls", namespace="v2_analytics")),
    path("inbox/", include("apps.inbox.urls", namespace="v2_inbox")),
    path("ai/", include("apps.ai_engine.urls", namespace="v2_ai_engine")),
    path("automation/", include("apps.automation.urls", namespace="v2_automation")),
]
