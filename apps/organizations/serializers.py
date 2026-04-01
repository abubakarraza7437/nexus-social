"""
Organizations — Serializers
============================
Covers Organisation read, member management, invitation flows, and
secure organization onboarding (check-or-create, join requests).
"""
import re

from rest_framework import serializers

from .models import JoinRequest, Organization, OrganizationMember


# ---------------------------------------------------------------------------
# Nested user representation (read-only, used inside member serializer)
# ---------------------------------------------------------------------------

class _UserInlineSerializer(serializers.Serializer):
    """Minimal read-only user representation embedded in member payloads."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.CharField(read_only=True)


# ---------------------------------------------------------------------------
# Organisation
# ---------------------------------------------------------------------------

class OrganizationSerializer(serializers.ModelSerializer):
    """Read-only serializer for Organisation instances."""

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "schema_name",
            "plan",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "slug",
            "schema_name",
            "plan",
            "is_active",
            "created_at",
        ]


# ---------------------------------------------------------------------------
# OrganizationMember
# ---------------------------------------------------------------------------

class OrganizationMemberSerializer(serializers.ModelSerializer):
    """
    Serializer for OrganizationMember instances.

    Embeds a nested read-only user representation instead of exposing the raw
    FK integer so clients receive usable identity information.
    """

    user = _UserInlineSerializer(read_only=True)
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = OrganizationMember
        fields = [
            "id",
            "user",
            "organization_id",
            "role",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "organization_id",
            "is_active",
            "created_at",
        ]


# ---------------------------------------------------------------------------
# Invite
# ---------------------------------------------------------------------------

class InviteSerializer(serializers.Serializer):
    """Validate the payload for the POST /orgs/{id}/invite/ endpoint."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=OrganizationMember.Role.choices,
        default=OrganizationMember.Role.MEMBER,
    )


# ---------------------------------------------------------------------------
# Join via invitation token
# ---------------------------------------------------------------------------

class JoinOrganizationSerializer(serializers.Serializer):
    """Validate the payload for the POST /orgs/join/ endpoint."""

    token = serializers.CharField()


# ---------------------------------------------------------------------------
# Update member role
# ---------------------------------------------------------------------------

class UpdateMemberRoleSerializer(serializers.Serializer):
    """Validate the PATCH payload for the member-detail endpoint."""

    role = serializers.ChoiceField(choices=OrganizationMember.Role.choices)


# ---------------------------------------------------------------------------
# Organization Onboarding — Check or Create
# ---------------------------------------------------------------------------

class CheckOrCreateOrganizationSerializer(serializers.Serializer):
    """
    Validate the payload for POST /orgs/check-or-create/.

    Input: organization_name
    Output varies based on whether org exists:
      - exists=True  → org_id, name (user must request to join)
      - exists=False → full org details (org created, user is OWNER)
    """

    organization_name = serializers.CharField(
        min_length=2,
        max_length=255,
        help_text="Name of the organization to check or create.",
    )

    def validate_organization_name(self, value: str) -> str:
        """
        Validate organization name:
        - Strip whitespace
        - Check for valid characters (alphanumeric, spaces, hyphens, underscores)
        - Prevent names that are too generic or reserved
        """
        value = value.strip()

        # Check for valid characters
        if not re.match(r"^[\w\s\-\.]+$", value, re.UNICODE):
            raise serializers.ValidationError(
                "Organization name can only contain letters, numbers, spaces, "
                "hyphens, underscores, and periods."
            )

        # Prevent reserved/generic names
        reserved_names = {
            "admin", "administrator", "system", "public", "private",
            "test", "demo", "example", "support", "help", "api",
            "www", "mail", "email", "root", "null", "undefined",
        }
        if value.lower() in reserved_names:
            raise serializers.ValidationError(
                "This organization name is reserved and cannot be used."
            )

        return value


class CheckOrCreateOrganizationResponseSerializer(serializers.Serializer):
    """Response serializer for check-or-create endpoint."""

    exists = serializers.BooleanField()
    organization = OrganizationSerializer(required=False)
    org_id = serializers.UUIDField(required=False)
    org_name = serializers.CharField(required=False)
    message = serializers.CharField()


# ---------------------------------------------------------------------------
# Join Request — Create
# ---------------------------------------------------------------------------

class CreateJoinRequestSerializer(serializers.Serializer):
    """
    Validate the payload for POST /orgs/request-join/.

    Creates a join request for an existing organization.
    """

    org_id = serializers.UUIDField(
        help_text="UUID of the organization to request joining.",
    )
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Optional message explaining why you want to join.",
    )

    def validate_org_id(self, value):
        """Ensure the organization exists and is active."""
        try:
            org = Organization.objects.get(pk=value, is_active=True)        # noqa
        except Organization.DoesNotExist:
            raise serializers.ValidationError("Organization not found or inactive.")
        return value

    def validate(self, attrs):
        """
        Additional validation:
        - User must not already be a member
        - User must not have a pending request
        - User's email should be verified (recommended)
        """
        user = self.context.get("user")
        org_id = attrs.get("org_id")

        if not user:
            raise serializers.ValidationError("User context is required.")

        # Check if user is already a member
        if OrganizationMember.objects.filter(
            organization_id=org_id,
            user=user,
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                {"org_id": "You are already a member of this organization."}
            )

        # Check for existing pending request
        if JoinRequest.objects.filter(
            organization_id=org_id,
            user=user,
            status=JoinRequest.Status.PENDING,
        ).exists():
            raise serializers.ValidationError(
                {"org_id": "You already have a pending request for this organization."}
            )

        # Recommended: Check email verification
        if not user.is_verified:
            raise serializers.ValidationError(
                "Please verify your email address before requesting to join an organization."
            )

        return attrs


# ---------------------------------------------------------------------------
# Join Request — Read
# ---------------------------------------------------------------------------

class JoinRequestSerializer(serializers.ModelSerializer):
    """Read serializer for JoinRequest instances."""

    user = _UserInlineSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True)
    reviewed_by = _UserInlineSerializer(read_only=True)

    class Meta:
        model = JoinRequest
        fields = [
            "id",
            "user",
            "organization",
            "status",
            "message",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "created_at",
            "expires_at",
        ]
        read_only_fields = fields


class JoinRequestListSerializer(serializers.ModelSerializer):
    """Compact serializer for listing join requests (admin view)."""

    user = _UserInlineSerializer(read_only=True)

    class Meta:
        model = JoinRequest
        fields = [
            "id",
            "user",
            "status",
            "message",
            "created_at",
            "expires_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Join Request — Approve/Reject
# ---------------------------------------------------------------------------

class ApproveJoinRequestSerializer(serializers.Serializer):
    """Validate the payload for POST /orgs/{id}/join-requests/{request_id}/approve/."""

    role = serializers.ChoiceField(
        choices=OrganizationMember.Role.choices,
        default=OrganizationMember.Role.MEMBER,
        help_text="Role to assign to the new member (defaults to MEMBER).",
    )


class RejectJoinRequestSerializer(serializers.Serializer):
    """Validate the payload for POST /orgs/{id}/join-requests/{request_id}/reject/."""

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Optional reason for rejection (shared with the requester).",
    )
