"""
Organizations v2 — Views
=========================
Extends v1 views with richer data and adds new endpoints.

v2 changes
----------
``OrganizationListViewV2``   — annotates queryset with member_count (no N+1).
``OrganizationDetailViewV2`` — same annotation; uses OrganizationSerializerV2.
``MemberListViewV2``         — adds joined_at + invited_by_email via v2 serializer.
``OrganizationStatsView``    — NEW: GET /api/v2/orgs/{id}/stats/

Unchanged endpoints (re-exported from v1)
------------------------------------------
All write/mutation endpoints are identical in v1 and v2 — no need to override:
  InviteView, JoinOrganizationView, MemberDetailView,
  CheckOrCreateOrganizationView, RequestJoinView, JoinRequestListView,
  ApproveJoinRequestView, RejectJoinRequestView, MyJoinRequestsView,
  CancelJoinRequestView
"""
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import JoinRequest, Organization, OrganizationInvitation, OrganizationMember

# Re-export unchanged v1 views so v2/urls.py only needs to import from here.
from ..v1.views import (  # noqa: F401
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
    _get_membership_or_403,
    _get_org_or_404,
)

from .serializers import (
    OrganizationMemberSerializerV2,
    OrganizationSerializerV2,
    OrganizationStatsSerializer,
)


def _annotated_org_qs(user):
    """Orgs the user belongs to, annotated with active member_count."""
    return (
        Organization.objects.filter(
            members__user=user,
            members__is_active=True,
        )
        .annotate(
            member_count=Count(
                "members",
                filter=Q(members__is_active=True),
            )
        )
        .distinct()
    )


class OrganizationListViewV2(ListAPIView):
    """
    GET /api/v2/orgs/

    Returns the user's organisations enriched with member_count,
    updated_at, and plan_limits.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationSerializerV2

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Organization.objects.none()
        return _annotated_org_qs(self.request.user)


class OrganizationDetailViewV2(RetrieveAPIView):
    """
    GET /api/v2/orgs/{id}/

    Returns a single organisation enriched with v2 fields.
    Requester must be an active member.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationSerializerV2

    def get_object(self):
        org = _get_org_or_404(self.kwargs["pk"])
        _get_membership_or_403(self.request.user, org)
        return (
            Organization.objects.filter(pk=org.pk)
            .annotate(
                member_count=Count(
                    "members",
                    filter=Q(members__is_active=True),
                )
            )
            .get()
        )


class MemberListViewV2(ListAPIView):
    """
    GET /api/v2/orgs/{id}/members/

    Returns active members enriched with joined_at and invited_by_email.
    Requester must be an active member.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationMemberSerializerV2

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return OrganizationMember.objects.none()
        org = _get_org_or_404(self.kwargs["pk"])
        _get_membership_or_403(self.request.user, org)
        return (
            OrganizationMember.objects.filter(
                organization=org,
                is_active=True,
            )
            .select_related("user", "invited_by")
        )


class OrganizationStatsView(APIView):
    """
    GET /api/v2/orgs/{id}/stats/

    Returns a live summary of the organisation's key metrics.
    All counts are computed in a single query — no N+1.

    Response:
        {
          "org_id": "...",
          "org_name": "Acme Corp",
          "plan": "pro",
          "member_count": 12,
          "pending_join_requests": 3,
          "pending_invitations": 1,
          "plan_limits": { "max_members": 25, "max_posts": 500 }
        }

    Permission: any active member (OWNER, ADMIN, or MEMBER).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OrganizationStatsSerializer)
    def get(self, request, pk):
        org = _get_org_or_404(pk)
        _get_membership_or_403(request.user, org)

        member_count = OrganizationMember.objects.filter(
            organization=org, is_active=True,
        ).count()

        pending_join_requests = JoinRequest.objects.filter(
            organization=org, status=JoinRequest.Status.PENDING,
        ).count()

        pending_invitations = OrganizationInvitation.objects.filter(
            organization=org, is_used=False,
        ).count()

        data = {
            "org_id": str(org.pk),
            "org_name": org.name,
            "plan": org.plan,
            "member_count": member_count,
            "pending_join_requests": pending_join_requests,
            "pending_invitations": pending_invitations,
            "plan_limits": org.plan_limits,
        }
        return Response(OrganizationStatsSerializer(data).data)
