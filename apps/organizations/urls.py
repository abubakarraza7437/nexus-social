"""
Organizations — URL patterns.
"""
from django.urls import path

from .views import (
    InviteView,
    JoinOrganizationView,
    MemberDetailView,
    MemberListView,
    OrganizationDetailView,
    OrganizationListView,
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
]
