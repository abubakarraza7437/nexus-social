"""
Organizations — Views
=====================
All endpoints require an authenticated user (IsAuthenticated is the global
DRF default; each view sets permission_classes explicitly for clarity).

URL layout (prefix /api/v1/orgs/):
  GET    /                                              → OrganizationListView
  GET    /{id}/                                         → OrganizationDetailView
  POST   /{id}/invite/                                  → InviteView
  POST   /join/                                         → JoinOrganizationView
  GET    /{id}/members/                                 → MemberListView
  PATCH  /{id}/members/{member_id}/                     → MemberDetailView (update role)
  DELETE /{id}/members/{member_id}/                     → MemberDetailView (remove member)

  # Organization Onboarding (post-signup flow)
  POST   /check-or-create/                              → CheckOrCreateOrganizationView
  POST   /request-join/                                 → RequestJoinView
  GET    /{id}/join-requests/                           → JoinRequestListView
  POST   /{id}/join-requests/{request_id}/approve/      → ApproveJoinRequestView
  POST   /{id}/join-requests/{request_id}/reject/       → RejectJoinRequestView
  GET    /my-join-requests/                             → MyJoinRequestsView
  DELETE /my-join-requests/{request_id}/                → CancelJoinRequestView
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_core.services import send_invitation_email

from .models import JoinRequest, Organization, OrganizationInvitation, OrganizationMember
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
from .services import (
    approve_join_request,
    check_organization_exists,
    create_invitation,
    create_join_request,
    create_organization_with_owner,
    notify_admins_of_join_request,
    notify_user_of_request_decision,
    reject_join_request,
)

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


# ===========================================================================
# ORGANIZATION ONBOARDING VIEWS (Post-Signup Flow)
# ===========================================================================


# ---------------------------------------------------------------------------
# Check or Create Organization
# ---------------------------------------------------------------------------

class CheckOrCreateOrganizationView(APIView):
    """
    POST /orgs/check-or-create/

    Post-signup organization onboarding endpoint.

    Input: { "organization_name": "Acme Corp" }

    Behavior:
    - If organization exists (case-insensitive match):
        → Return { "exists": true, "org_id": ..., "org_name": ... }
        → User must then call /orgs/request-join/ to request access
    - If organization does NOT exist:
        → Create new organization
        → Create schema (django-tenants)
        → Create domain entry
        → Make current user the OWNER
        → Return { "exists": false, "organization": {...} }

    Security:
    - User must be authenticated
    - User's email should be verified (enforced in serializer)
    - No auto-join to existing organizations
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CheckOrCreateOrganizationSerializer

    def post(self, request):
        serializer = CheckOrCreateOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org_name = serializer.validated_data["organization_name"]
        user = request.user

        # Check email verification (security requirement)
        if not user.is_verified:
            return Response(
                {
                    "detail": "Please verify your email address before creating "
                    "or joining an organization."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if organization exists (case-insensitive)
        existing_org = check_organization_exists(org_name)

        if existing_org:
            # Organization exists — user must request to join
            # Check if user is already a member
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

            # Check if user has a pending request
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
                    "message": (
                        "This organization already exists. "
                        "Would you like to request to join?"
                    ),
                },
                status=status.HTTP_200_OK,
            )

        # Organization does not exist — create it with user as OWNER
        try:
            org, membership = create_organization_with_owner(
                name=org_name,
                owner_user=user,
            )
        except ValueError as e:
            # Race condition: org was created between check and create
            return Response(
                {"detail": str(e)},
                status=status.HTTP_409_CONFLICT,
            )

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
# Request to Join Organization
# ---------------------------------------------------------------------------

class RequestJoinView(APIView):
    """
    POST /orgs/request-join/

    Create a join request for an existing organization.

    Input: { "org_id": "uuid", "message": "optional message" }

    Security:
    - User must be authenticated
    - User's email must be verified
    - User must not already be a member
    - User must not have a pending request
    - Creates PENDING request that requires OWNER/ADMIN approval
    """

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
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Send notification to org admins (mock)
        notify_admins_of_join_request(join_request)

        return Response(
            {
                "detail": "Join request submitted successfully.",
                "request": JoinRequestSerializer(join_request).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# List Join Requests (Admin View)
# ---------------------------------------------------------------------------

class JoinRequestListView(ListAPIView):
    """
    GET /orgs/{id}/join-requests/

    List all join requests for an organization.
    Requester must be OWNER or ADMIN.

    Query params:
    - status: Filter by status (pending, approved, rejected, expired, cancelled)
    """

    permission_classes = [IsAuthenticated]
    serializer_class = JoinRequestListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return JoinRequest.objects.none()

        org = _get_org_or_404(self.kwargs["pk"])
        requester = _get_membership_or_403(self.request.user, org)

        # Only OWNER or ADMIN can view join requests
        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only owners and admins can view join requests."
            )

        queryset = JoinRequest.objects.filter(
            organization=org,
        ).select_related("user").order_by("-created_at")

        # Optional status filter
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset


# ---------------------------------------------------------------------------
# Approve Join Request
# ---------------------------------------------------------------------------

class ApproveJoinRequestView(APIView):
    """
    POST /orgs/{id}/join-requests/{request_id}/approve/

    Approve a pending join request.
    Requester must be OWNER or ADMIN.

    Input: { "role": "member" }  (optional, defaults to "member")
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ApproveJoinRequestSerializer

    def post(self, request, pk, request_id):
        org = _get_org_or_404(pk)
        requester = _get_membership_or_403(request.user, org)

        # Only OWNER or ADMIN can approve
        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only owners and admins can approve join requests."
            )

        # Get the join request
        try:
            join_request = JoinRequest.objects.get(
                id=request_id,
                organization=org,
            )
        except JoinRequest.DoesNotExist:
            raise NotFound("Join request not found.")

        serializer = ApproveJoinRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role = serializer.validated_data.get("role", OrganizationMember.Role.MEMBER)

        # Only OWNER can assign OWNER or ADMIN roles
        if role in (OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN):
            if requester.role != OrganizationMember.Role.OWNER:
                raise PermissionDenied(
                    "Only owners can assign owner or admin roles."
                )

        try:
            membership = approve_join_request(
                join_request=join_request,
                reviewer=request.user,
                role=role,
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Notify the user (mock)
        notify_user_of_request_decision(join_request, approved=True)

        return Response(
            {
                "detail": "Join request approved.",
                "membership": OrganizationMemberSerializer(membership).data,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Reject Join Request
# ---------------------------------------------------------------------------

class RejectJoinRequestView(APIView):
    """
    POST /orgs/{id}/join-requests/{request_id}/reject/

    Reject a pending join request.
    Requester must be OWNER or ADMIN.

    Input: { "reason": "optional rejection reason" }
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RejectJoinRequestSerializer

    def post(self, request, pk, request_id):
        org = _get_org_or_404(pk)
        requester = _get_membership_or_403(request.user, org)

        # Only OWNER or ADMIN can reject
        if requester.role not in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only owners and admins can reject join requests."
            )

        # Get the join request
        try:
            join_request = JoinRequest.objects.get(
                id=request_id,
                organization=org,
            )
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
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Notify the user (mock)
        notify_user_of_request_decision(join_request, approved=False)

        return Response(
            {
                "detail": "Join request rejected.",
                "request": JoinRequestSerializer(join_request).data,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# My Join Requests (User View)
# ---------------------------------------------------------------------------

class MyJoinRequestsView(ListAPIView):
    """
    GET /orgs/my-join-requests/

    List all join requests made by the current user.
    """

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


# ---------------------------------------------------------------------------
# Cancel Join Request
# ---------------------------------------------------------------------------

class CancelJoinRequestView(APIView):
    """
    DELETE /orgs/my-join-requests/{request_id}/

    Cancel a pending join request.
    Only the requesting user can cancel their own request.
    """

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

        return Response(
            {"detail": "Join request cancelled."},
            status=status.HTTP_200_OK,
        )
