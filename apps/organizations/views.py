"""
Organizations — Views
=====================
All endpoints require an authenticated user (IsAuthenticated is the global
DRF default; each view sets permission_classes explicitly for clarity).

URL layout (prefix /api/v1/orgs/):
  GET    /                          → OrganizationListView
  GET    /{id}/                     → OrganizationDetailView
  POST   /{id}/invite/              → InviteView
  POST   /join/                     → JoinOrganizationView
  GET    /{id}/members/             → MemberListView
  PATCH  /{id}/members/{member_id}/ → MemberDetailView (update role)
  DELETE /{id}/members/{member_id}/ → MemberDetailView (remove member)
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_core.services import send_invitation_email

from .models import Organization, OrganizationInvitation, OrganizationMember
from .serializers import (
    InviteSerializer,
    JoinOrganizationSerializer,
    OrganizationMemberSerializer,
    OrganizationSerializer,
    UpdateMemberRoleSerializer,
)
from .services import create_invitation

User = get_user_model()


# ---------------------------------------------------------------------------
# Module-level helpers (reused across views)
# ---------------------------------------------------------------------------

def _get_org_or_404(pk) -> Organization:
    """Return the Organisation for *pk* or raise NotFound."""
    try:
        return Organization.objects.get(pk=pk)
    except Organization.DoesNotExist:
        raise NotFound("Organization not found.")


def _get_membership_or_403(user, org) -> OrganizationMember:
    """Return the active membership for *user* in *org* or raise PermissionDenied."""
    try:
        return OrganizationMember.objects.get(
            organization=org,
            user=user,
            is_active=True,
        )
    except OrganizationMember.DoesNotExist:
        raise PermissionDenied("You are not a member of this organization.")


# ---------------------------------------------------------------------------
# Organisation list / detail
# ---------------------------------------------------------------------------

class OrganizationListView(ListAPIView):
    """
    GET /orgs/
    Return all organisations where the authenticated user is an active member.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Organization.objects.none()
        return (
            Organization.objects.filter(
                members__user=self.request.user,
                members__is_active=True,
            )
            .distinct()
        )


class OrganizationDetailView(RetrieveAPIView):
    """
    GET /orgs/{id}/
    Return a single organisation; requester must be an active member.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationSerializer

    def get_object(self):
        org = _get_org_or_404(self.kwargs["pk"])
        _get_membership_or_403(self.request.user, org)
        return org


# ---------------------------------------------------------------------------
# Invite
# ---------------------------------------------------------------------------

class InviteView(APIView):
    """
    POST /orgs/{id}/invite/
    Send an email invitation; requester must be OWNER or ADMIN.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = InviteSerializer

    def post(self, request, pk):
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org = _get_org_or_404(pk)
        requester_membership = _get_membership_or_403(request.user, org)

        # Only OWNER or ADMIN can invite.
        if requester_membership.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only owners and admins can invite members."
            )

        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        # Check invitee is not already an active member.
        existing_user_qs = User.objects.filter(email__iexact=email)
        if existing_user_qs.exists():
            existing_user = existing_user_qs.first()
            if OrganizationMember.objects.filter(
                organization=org,
                user=existing_user,
                is_active=True,
            ).exists():
                raise ValidationError(
                    {"email": ["This user is already a member of the organization."]}
                )

        invitation = create_invitation(org, request.user, email, role)
        send_invitation_email(email, org, invitation.token)

        return Response(
            {"detail": "Invitation sent.", "token": invitation.token},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Join via token
# ---------------------------------------------------------------------------

class JoinOrganizationView(APIView):
    """
    POST /orgs/join/
    Accept an invitation token and create an OrganizationMember record.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = JoinOrganizationSerializer

    def post(self, request):
        serializer = JoinOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_value = serializer.validated_data["token"]

        try:
            invitation = OrganizationInvitation.objects.get(
                token=token_value,
                is_used=False,
            )
        except OrganizationInvitation.DoesNotExist:
            return Response(
                {"token": ["Invalid or expired token."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.is_expired:
            return Response(
                {"token": ["Invitation has expired."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Invitation must be addressed to the authenticated user's email.
        if invitation.email.lower() != request.user.email.lower():
            return Response(
                {
                    "detail": (
                        "This invitation was sent to a different email address."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        org = invitation.organization

        # Guard against duplicate membership.
        if OrganizationMember.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
        ).exists():
            return Response(
                {"detail": "You are already a member of this organization."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        OrganizationMember.objects.create(
            organization=org,
            user=request.user,
            role=invitation.role,
            invited_by=invitation.invited_by,
        )

        invitation.is_used = True
        invitation.save(update_fields=["is_used"])

        return Response(
            OrganizationSerializer(org).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Member list
# ---------------------------------------------------------------------------

class MemberListView(ListAPIView):
    """
    GET /orgs/{id}/members/
    Return active members of the organisation; requester must be a member.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationMemberSerializer

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
            .select_related("user")
        )


# ---------------------------------------------------------------------------
# Member detail — role update + removal
# ---------------------------------------------------------------------------

class MemberDetailView(APIView):
    """
    PATCH /orgs/{id}/members/{member_id}/ — update member role.
    DELETE /orgs/{id}/members/{member_id}/ — deactivate member.

    Requester must be OWNER or ADMIN.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UpdateMemberRoleSerializer

    def _get_target_member(self, org, member_id) -> OrganizationMember:
        try:
            return OrganizationMember.objects.get(
                id=member_id,
                organization=org,
                is_active=True,
            )
        except OrganizationMember.DoesNotExist:
            raise NotFound("Member not found.")

    def patch(self, request, pk, member_id):
        org = _get_org_or_404(pk)
        requester = _get_membership_or_403(request.user, org)

        # Only OWNER or ADMIN can change roles.
        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only owners and admins can update member roles."
            )

        target = self._get_target_member(org, member_id)

        serializer = UpdateMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        # Cannot change your own role via this endpoint.
        if target.user_id == request.user.pk:
            raise PermissionDenied("You cannot change your own role.")

        # Only an OWNER can assign the OWNER role.
        if (
            new_role == OrganizationMember.Role.OWNER
            and requester.role != OrganizationMember.Role.OWNER
        ):
            raise PermissionDenied("Only an owner can assign the owner role.")

        # Prevent removing the last OWNER by role-demotion.
        if target.role == OrganizationMember.Role.OWNER:
            owner_count = OrganizationMember.objects.filter(
                organization=org,
                role=OrganizationMember.Role.OWNER,
                is_active=True,
            ).count()
            if owner_count <= 1 and new_role != OrganizationMember.Role.OWNER:
                raise PermissionDenied(
                    "Cannot change the role of the only remaining owner."
                )

        target.role = new_role
        target.save(update_fields=["role"])

        return Response(
            OrganizationMemberSerializer(target).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk, member_id):
        org = _get_org_or_404(pk)
        requester = _get_membership_or_403(request.user, org)

        # Only OWNER or ADMIN can remove members.
        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only owners and admins can remove members."
            )

        target = self._get_target_member(org, member_id)

        # Cannot remove yourself via this endpoint (use a dedicated leave endpoint).
        if target.user_id == request.user.pk:
            raise PermissionDenied(
                "You cannot remove yourself. Use the leave organization endpoint."
            )

        # ADMIN cannot remove an OWNER.
        if (
            target.role == OrganizationMember.Role.OWNER
            and requester.role != OrganizationMember.Role.OWNER
        ):
            raise PermissionDenied("Admins cannot remove owners.")

        # Protect the last OWNER.
        if target.role == OrganizationMember.Role.OWNER:
            owner_count = OrganizationMember.objects.filter(
                organization=org,
                role=OrganizationMember.Role.OWNER,
                is_active=True,
            ).count()
            if owner_count <= 1:
                raise PermissionDenied(
                    "Cannot remove the only remaining owner of the organization."
                )

        target.is_active = False
        target.save(update_fields=["is_active"])

        return Response(status=status.HTTP_204_NO_CONTENT)
