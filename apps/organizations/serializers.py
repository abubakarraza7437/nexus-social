"""
Organizations — Serializers (backward-compat shim)
====================================================
Canonical location is now apps/organizations/v1/serializers.py.

Re-exports everything from v1 so existing imports continue to work.
"""
from .v1.serializers import (  # noqa: F401
    ApproveJoinRequestSerializer,
    CheckOrCreateOrganizationResponseSerializer,
    CheckOrCreateOrganizationSerializer,
    CreateJoinRequestSerializer,
    InviteSerializer,
    JoinOrganizationSerializer,
    JoinRequestListSerializer,
    JoinRequestSerializer,
    OrganizationMemberSerializer,
    OrganizationSerializer,
    RejectJoinRequestSerializer,
    UpdateMemberRoleSerializer,
)
