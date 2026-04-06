"""
API v2 — Central Router
========================
Pure routing — no views or serializers live here.
Each app owns its own v2/ subpackage with views, serializers, and urls.

Override vs. fall-through table
---------------------------------
  App               | v2 subpackage? | Notes
  ------------------|----------------|----------------------------------------------
  auth_core         | YES            | Login/signup return user profile object
  organizations     | YES            | Orgs+members enriched; /stats/ endpoint added
  social-accounts   | no (fall-thru) | Stub — implement v2 in apps/social_accounts/v2/
  content           | no (fall-thru) | Stub
  analytics         | no (fall-thru) | Stub
  inbox             | no (fall-thru) | Stub
  ai_engine         | no (fall-thru) | Stub
  automation        | no (fall-thru) | Stub

Fall-through apps use namespace prefix "v2_*" to prevent collision with v1.
Mounted at /api/v2/ in socialos/urls.py.
"""
from django.urls import include, path

urlpatterns = [
    # Implemented apps — v2 subpackages
    path("auth/", include("apps.auth_core.v2.urls", namespace="auth_v2")),
    path("orgs/", include("apps.organizations.v2.urls", namespace="organizations_v2")),

    # Stub apps — fall through to the same urls.py as v1
    path("social-accounts/", include("apps.social_accounts.urls", namespace="v2_social_accounts")),
    path("posts/", include("apps.content.urls", namespace="v2_content")),
    path("analytics/", include("apps.analytics.urls", namespace="v2_analytics")),
    path("inbox/", include("apps.inbox.urls", namespace="v2_inbox")),
    path("ai/", include("apps.ai_engine.urls", namespace="v2_ai_engine")),
    path("automation/", include("apps.automation.urls", namespace="v2_automation")),
]
