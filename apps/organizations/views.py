"""
Organizations — Views (backward-compat shim)
=============================================
Canonical location is now apps/organizations/v1/views.py.

Re-exports everything from v1 so existing imports continue to work.
"""
from apps.auth_core.services import send_invitation_email  # noqa: F401

from .v1.views import (  # noqa: F401
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
    _get_membership_or_403,
    _get_org_or_404,
)
