"""
Organizations v1 — URL patterns.
Mounted at /api/v1/orgs/ via api/v1/urls.py.
"""
from django.urls import path

from .views import (
    ApproveJoinRequestView,
    CancelJoinRequestView,
    CheckOrCreateOrganizationView,
    InviteView,
    JoinOrganizationView,
    JoinRequestListView,
    MemberDetailView,
    MemberListView,
    MyJoinRequestsView,
    OrganizationDetailView,
    OrganizationListView,
    RejectJoinRequestView,
    RequestJoinView,
)

app_name = "organizations"

urlpatterns = [
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
    path("check-or-create/", CheckOrCreateOrganizationView.as_view(), name="org-check-or-create"),
    path("request-join/", RequestJoinView.as_view(), name="org-request-join"),
    path("my-join-requests/", MyJoinRequestsView.as_view(), name="org-my-join-requests"),
    path(
        "my-join-requests/<uuid:request_id>/",
        CancelJoinRequestView.as_view(),
        name="org-cancel-join-request",
    ),
    path("<uuid:pk>/join-requests/", JoinRequestListView.as_view(), name="org-join-request-list"),
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
