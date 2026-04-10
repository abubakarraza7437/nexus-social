from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_core.services import send_invitation_email

from ..models import JoinRequest, Organization, OrganizationInvitation, OrganizationMember
from ..services import (
    approve_join_request,
    check_organization_exists,
    create_invitation,
    create_join_request,
    create_organization_with_owner,
    notify_admins_of_join_request,
    notify_user_of_request_decision,
    reject_join_request,
)
from .serializers import (
    ApproveJoinRequestSerializer,
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

User = get_user_model()


# ---------------------------------------------------------------------------
# Module-level helpers (reused across views and re-exported to v2)
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
    """GET /api/v1/orgs/ — list organisations the authenticated user belongs to."""

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
    """GET /api/v1/orgs/{id}/ — retrieve a single org; requester must be a member."""

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
    """POST /api/v1/orgs/{id}/invite/ — send an email invite; requester must be OWNER or ADMIN."""

    permission_classes = [IsAuthenticated]
    serializer_class = InviteSerializer

    def post(self, request, pk):
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org = _get_org_or_404(pk)
        requester_membership = _get_membership_or_403(request.user, org)

        if requester_membership.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied("Only owners and admins can invite members.")

        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

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
    """POST /api/v1/orgs/join/ — accept an invitation token."""

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

        if invitation.email.lower() != request.user.email.lower():
            return Response(
                {"detail": "This invitation was sent to a different email address."},
                status=status.HTTP_403_FORBIDDEN,
            )

        org = invitation.organization

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
# Member list / detail
# ---------------------------------------------------------------------------

class MemberListView(ListAPIView):
    """GET /api/v1/orgs/{id}/members/ — list active members; requester must be a member."""

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


class MemberDetailView(APIView):
    """
    PATCH /api/v1/orgs/{id}/members/{member_id}/ — update member role.
    DELETE /api/v1/orgs/{id}/members/{member_id}/ — deactivate member.
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

        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied("Only owners and admins can update member roles.")

        target = self._get_target_member(org, member_id)
        serializer = UpdateMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        if target.user_id == request.user.pk:
            raise PermissionDenied("You cannot change your own role.")

        if (
            new_role == OrganizationMember.Role.OWNER
            and requester.role != OrganizationMember.Role.OWNER
        ):
            raise PermissionDenied("Only an owner can assign the owner role.")

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

        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied("Only owners and admins can remove members.")

        target = self._get_target_member(org, member_id)

        if target.user_id == request.user.pk:
            raise PermissionDenied(
                "You cannot remove yourself. Use the leave organization endpoint."
            )

        if (
            target.role == OrganizationMember.Role.OWNER
            and requester.role != OrganizationMember.Role.OWNER
        ):
            raise PermissionDenied("Admins cannot remove owners.")

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


# ---------------------------------------------------------------------------
# Onboarding — Check or Create
# ---------------------------------------------------------------------------

class CheckOrCreateOrganizationView(APIView):
    """POST /api/v1/orgs/check-or-create/ — post-signup onboarding flow."""

    permission_classes = [IsAuthenticated]
    serializer_class = CheckOrCreateOrganizationSerializer

    def post(self, request):
        serializer = CheckOrCreateOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org_name = serializer.validated_data["organization_name"]
        user = request.user

        if not user.is_verified:
            return Response(
                {"detail": "Please verify your email address before creating or joining an organization."},
                status=status.HTTP_403_FORBIDDEN,
            )

        existing_org = check_organization_exists(org_name)

        if existing_org:
            if OrganizationMember.objects.filter(
                organization=existing_org,
                user=user,
                is_active=True,
            ).exists():
                return Response(
                    {
                        "exists": True,
                        "already_member": True,
                        "organization": OrganizationSerializer(existing_org).data,
                        "message": "You are already a member of this organization.",
                    },
                    status=status.HTTP_200_OK,
                )

            pending_request = JoinRequest.objects.filter(
                organization=existing_org,
                user=user,
                status=JoinRequest.Status.PENDING,
            ).first()

            if pending_request and pending_request.is_pending:
                return Response(
                    {
                        "exists": True,
                        "pending_request": True,
                        "org_id": str(existing_org.id),
                        "org_name": existing_org.name,
                        "request_id": str(pending_request.id),
                        "message": "You already have a pending request to join this organization.",
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(
                {
                    "exists": True,
                    "org_id": str(existing_org.id),
                    "org_name": existing_org.name,
                    "message": "This organization already exists. Would you like to request to join?",
                },
                status=status.HTTP_200_OK,
            )

        try:
            org, membership = create_organization_with_owner(
                name=org_name,
                owner_user=user,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        return Response(
            {
                "exists": False,
                "organization": OrganizationSerializer(org).data,
                "membership": OrganizationMemberSerializer(membership).data,
                "message": "Organization created successfully. You are the owner.",
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Onboarding — Request to Join
# ---------------------------------------------------------------------------

class RequestJoinView(APIView):
    """POST /api/v1/orgs/request-join/ — submit a join request."""

    permission_classes = [IsAuthenticated]
    serializer_class = CreateJoinRequestSerializer

    def post(self, request):
        serializer = CreateJoinRequestSerializer(
            data=request.data,
            context={"user": request.user},
        )
        serializer.is_valid(raise_exception=True)

        org_id = serializer.validated_data["org_id"]
        message = serializer.validated_data.get("message", "")
        org = Organization.objects.get(pk=org_id)

        try:
            join_request = create_join_request(
                user=request.user,
                organization=org,
                message=message,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        notify_admins_of_join_request(join_request)

        return Response(
            {
                "detail": "Join request submitted successfully.",
                "request": JoinRequestSerializer(join_request).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Onboarding — Join Request management
# ---------------------------------------------------------------------------

class JoinRequestListView(ListAPIView):
    """GET /api/v1/orgs/{id}/join-requests/ — admin: list join requests."""

    permission_classes = [IsAuthenticated]
    serializer_class = JoinRequestListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return JoinRequest.objects.none()

        org = _get_org_or_404(self.kwargs["pk"])
        requester = _get_membership_or_403(self.request.user, org)

        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied("Only owners and admins can view join requests.")

        queryset = JoinRequest.objects.filter(organization=org).select_related("user").order_by("-created_at")

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset


class ApproveJoinRequestView(APIView):
    """POST /api/v1/orgs/{id}/join-requests/{request_id}/approve/"""

    permission_classes = [IsAuthenticated]
    serializer_class = ApproveJoinRequestSerializer

    def post(self, request, pk, request_id):
        org = _get_org_or_404(pk)
        requester = _get_membership_or_403(request.user, org)

        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied("Only owners and admins can approve join requests.")

        try:
            join_request = JoinRequest.objects.get(id=request_id, organization=org)
        except JoinRequest.DoesNotExist:
            raise NotFound("Join request not found.")

        serializer = ApproveJoinRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = serializer.validated_data.get("role", OrganizationMember.Role.MEMBER)

        if role in (OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN):
            if requester.role != OrganizationMember.Role.OWNER:
                raise PermissionDenied("Only owners can assign owner or admin roles.")

        try:
            membership = approve_join_request(
                join_request=join_request,
                reviewer=request.user,
                role=role,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        notify_user_of_request_decision(join_request, approved=True)

        return Response(
            {
                "detail": "Join request approved.",
                "membership": OrganizationMemberSerializer(membership).data,
            },
            status=status.HTTP_200_OK,
        )


class RejectJoinRequestView(APIView):
    """POST /api/v1/orgs/{id}/join-requests/{request_id}/reject/"""

    permission_classes = [IsAuthenticated]
    serializer_class = RejectJoinRequestSerializer

    def post(self, request, pk, request_id):
        org = _get_org_or_404(pk)
        requester = _get_membership_or_403(request.user, org)

        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied("Only owners and admins can reject join requests.")

        try:
            join_request = JoinRequest.objects.get(id=request_id, organization=org)
        except JoinRequest.DoesNotExist:
            raise NotFound("Join request not found.")

        serializer = RejectJoinRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        try:
            join_request = reject_join_request(
                join_request=join_request,
                reviewer=request.user,
                reason=reason,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        notify_user_of_request_decision(join_request, approved=False)

        return Response(
            {
                "detail": "Join request rejected.",
                "request": JoinRequestSerializer(join_request).data,
            },
            status=status.HTTP_200_OK,
        )


class MyJoinRequestsView(ListAPIView):
    """GET /api/v1/orgs/my-join-requests/ — list the current user's own join requests."""

    permission_classes = [IsAuthenticated]
    serializer_class = JoinRequestSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return JoinRequest.objects.none()
        return (
            JoinRequest.objects.filter(user=self.request.user)
            .select_related("organization", "reviewed_by")
            .order_by("-created_at")
        )


class CancelJoinRequestView(APIView):
    """DELETE /api/v1/orgs/my-join-requests/{request_id}/ — cancel a pending request."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, request_id):
        try:
            join_request = JoinRequest.objects.get(
                id=request_id,
                user=request.user,
            )
        except JoinRequest.DoesNotExist:
            raise NotFound("Join request not found.")

        if join_request.status != JoinRequest.Status.PENDING:
            return Response(
                {"detail": f"Cannot cancel a {join_request.status} request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        join_request.status = JoinRequest.Status.CANCELLED
        join_request.save(update_fields=["status", "updated_at"])

        return Response({"detail": "Join request cancelled."}, status=status.HTTP_200_OK)
