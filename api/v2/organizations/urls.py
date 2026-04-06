"""
Organizations v2 — URL patterns.

Mounted at /api/v2/orgs/ via api/v2/urls.py.

URL layout
----------
  # v2-enhanced read endpoints
  GET    /                                              → OrganizationListViewV2
  GET    /{id}/                                         → OrganizationDetailViewV2
  GET    /{id}/members/                                 → MemberListViewV2
  GET    /{id}/stats/                                   → OrganizationStatsView  ← NEW in v2

  # Unchanged from v1 (same view class, new URL registration)
  POST   /{id}/invite/                                  → InviteView
  POST   /join/                                         → JoinOrganizationView
  PATCH  /{id}/members/{member_id}/                     → MemberDetailView
  DELETE /{id}/members/{member_id}/                     → MemberDetailView
  POST   /check-or-create/                              → CheckOrCreateOrganizationView
  POST   /request-join/                                 → RequestJoinView
  GET    /{id}/join-requests/                           → JoinRequestListView
  POST   /{id}/join-requests/{request_id}/approve/      → ApproveJoinRequestView
  POST   /{id}/join-requests/{request_id}/reject/       → RejectJoinRequestView
  GET    /my-join-requests/                             → MyJoinRequestsView
  DELETE /my-join-requests/{request_id}/                → CancelJoinRequestView
"""
from django.urls import path

from .views import (
    # v2-specific views
    MemberListViewV2,
    OrganizationDetailViewV2,
    OrganizationListViewV2,
    OrganizationStatsView,
    # Re-exported v1 views (unchanged)
    ApproveJoinRequestView,
    CancelJoinRequestView,
    CheckOrCreateOrganizationView,
    InviteView,
    JoinOrganizationView,
    JoinRequestListView,
    MemberDetailView,
    MyJoinRequestsView,
    RejectJoinRequestView,
    RequestJoinView,
)

urlpatterns = [
    # -------------------------------------------------------------------------
    # v2-enhanced read endpoints
    # -------------------------------------------------------------------------
    path("", OrganizationListViewV2.as_view(), name="v2-org-list"),
    path("<uuid:pk>/", OrganizationDetailViewV2.as_view(), name="v2-org-detail"),
    path("<uuid:pk>/members/", MemberListViewV2.as_view(), name="v2-org-member-list"),
    path("<uuid:pk>/stats/", OrganizationStatsView.as_view(), name="v2-org-stats"),

    # -------------------------------------------------------------------------
    # Unchanged from v1
    # -------------------------------------------------------------------------
    path("<uuid:pk>/invite/", InviteView.as_view(), name="v2-org-invite"),
    path("join/", JoinOrganizationView.as_view(), name="v2-org-join"),
    path(
        "<uuid:pk>/members/<uuid:member_id>/",
        MemberDetailView.as_view(),
        name="v2-org-member-detail",
    ),
    path("check-or-create/", CheckOrCreateOrganizationView.as_view(), name="v2-org-check-or-create"),
    path("request-join/", RequestJoinView.as_view(), name="v2-org-request-join"),
    path("my-join-requests/", MyJoinRequestsView.as_view(), name="v2-org-my-join-requests"),
    path(
        "my-join-requests/<uuid:request_id>/",
        CancelJoinRequestView.as_view(),
        name="v2-org-cancel-join-request",
    ),
    path("<uuid:pk>/join-requests/", JoinRequestListView.as_view(), name="v2-org-join-request-list"),
    path(
        "<uuid:pk>/join-requests/<uuid:request_id>/approve/",
        ApproveJoinRequestView.as_view(),
        name="v2-org-approve-join-request",
    ),
    path(
        "<uuid:pk>/join-requests/<uuid:request_id>/reject/",
        RejectJoinRequestView.as_view(),
        name="v2-org-reject-join-request",
    ),
]
