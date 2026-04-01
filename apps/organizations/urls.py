"""
Organizations — URL patterns.

URL layout (prefix /api/v1/orgs/):
  # Core Organization endpoints
  GET    /                                              → OrganizationListView
  GET    /{id}/                                         → OrganizationDetailView
  POST   /{id}/invite/                                  → InviteView
  POST   /join/                                         → JoinOrganizationView
  GET    /{id}/members/                                 → MemberListView
  PATCH  /{id}/members/{member_id}/                     → MemberDetailView
  DELETE /{id}/members/{member_id}/                     → MemberDetailView

  # Organization Onboarding (post-signup flow)
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
    # Core views
    InviteView,
    JoinOrganizationView,
    MemberDetailView,
    MemberListView,
    OrganizationDetailView,
    OrganizationListView,
    # Onboarding views
    ApproveJoinRequestView,
    CancelJoinRequestView,
    CheckOrCreateOrganizationView,
    JoinRequestListView,
    MyJoinRequestsView,
    RejectJoinRequestView,
    RequestJoinView,
)

app_name = "organizations"

urlpatterns = [
    # -------------------------------------------------------------------------
    # Core Organization endpoints
    # -------------------------------------------------------------------------
    path("", OrganizationListView.as_view(), name="org-list"),
    path("<uuid:pk>/", OrganizationDetailView.as_view(), name="org-detail"),
    path("<uuid:pk>/invite/", InviteView.as_view(), name="org-invite"),
    path("join/", JoinOrganizationView.as_view(), name="org-join"),
    path("<uuid:pk>/members/", MemberListView.as_view(), name="org-member-list"),
    path(
        "<uuid:pk>/members/<uuid:member_id>/",
        MemberDetailView.as_view(),
        name="org-member-detail",
    ),

    # -------------------------------------------------------------------------
    # Organization Onboarding (post-signup flow)
    # -------------------------------------------------------------------------
    # Check if org exists or create new one
    path(
        "check-or-create/",
        CheckOrCreateOrganizationView.as_view(),
        name="org-check-or-create",
    ),

    # Request to join an existing organization
    path(
        "request-join/",
        RequestJoinView.as_view(),
        name="org-request-join",
    ),

    # User's own join requests
    path(
        "my-join-requests/",
        MyJoinRequestsView.as_view(),
        name="org-my-join-requests",
    ),
    path(
        "my-join-requests/<uuid:request_id>/",
        CancelJoinRequestView.as_view(),
        name="org-cancel-join-request",
    ),

    # Admin: List join requests for an organization
    path(
        "<uuid:pk>/join-requests/",
        JoinRequestListView.as_view(),
        name="org-join-request-list",
    ),

    # Admin: Approve/Reject join requests
    path(
        "<uuid:pk>/join-requests/<uuid:request_id>/approve/",
        ApproveJoinRequestView.as_view(),
        name="org-approve-join-request",
    ),
    path(
        "<uuid:pk>/join-requests/<uuid:request_id>/reject/",
        RejectJoinRequestView.as_view(),
        name="org-reject-join-request",
    ),
]
