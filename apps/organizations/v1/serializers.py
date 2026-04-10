import re

from rest_framework import serializers

from ..models import JoinRequest, Organization, OrganizationMember


class _UserInlineSerializer(serializers.Serializer):
    """Minimal read-only user representation embedded in member payloads."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.CharField(read_only=True)


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
        read_only_fields = fields


class OrganizationMemberSerializer(serializers.ModelSerializer):
    """Serializer for OrganizationMember instances with nested user."""

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
        read_only_fields = fields


class InviteSerializer(serializers.Serializer):
    """Validate the payload for POST /orgs/{id}/invite/."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=OrganizationMember.Role.choices,
        default=OrganizationMember.Role.MEMBER,
    )


class JoinOrganizationSerializer(serializers.Serializer):
    """Validate the payload for POST /orgs/join/."""

    token = serializers.CharField()


class UpdateMemberRoleSerializer(serializers.Serializer):
    """Validate the PATCH payload for the member-detail endpoint."""

    role = serializers.ChoiceField(choices=OrganizationMember.Role.choices)


class CheckOrCreateOrganizationSerializer(serializers.Serializer):
    """Validate POST /orgs/check-or-create/."""

    organization_name = serializers.CharField(
        min_length=2,
        max_length=255,
        help_text="Name of the organization to check or create.",
    )

    def validate_organization_name(self, value: str) -> str:
        value = value.strip()
        if not re.match(r"^[\w\s\-\.]+$", value, re.UNICODE):
            raise serializers.ValidationError(
                "Organization name can only contain letters, numbers, spaces, "
                "hyphens, underscores, and periods."
            )
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
    """Response shape for check-or-create endpoint (documentation only)."""

    exists = serializers.BooleanField()
    organization = OrganizationSerializer(required=False)
    org_id = serializers.UUIDField(required=False)
    org_name = serializers.CharField(required=False)
    message = serializers.CharField()


class CreateJoinRequestSerializer(serializers.Serializer):
    """Validate POST /orgs/request-join/."""

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
        try:
            Organization.objects.get(pk=value, is_active=True)
        except Organization.DoesNotExist:
            raise serializers.ValidationError("Organization not found or inactive.")
        return value

    def validate(self, attrs):
        user = self.context.get("user")
        org_id = attrs.get("org_id")

        if not user:
            raise serializers.ValidationError("User context is required.")

        if OrganizationMember.objects.filter(
            organization_id=org_id,
            user=user,
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                {"org_id": "You are already a member of this organization."}
            )

        if JoinRequest.objects.filter(
            organization_id=org_id,
            user=user,
            status=JoinRequest.Status.PENDING,
        ).exists():
            raise serializers.ValidationError(
                {"org_id": "You already have a pending request for this organization."}
            )

        if not user.is_verified:
            raise serializers.ValidationError(
                "Please verify your email address before requesting to join an organization."
            )

        return attrs


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
        fields = ["id", "user", "status", "message", "created_at", "expires_at"]
        read_only_fields = fields


class ApproveJoinRequestSerializer(serializers.Serializer):
    """Validate POST /orgs/{id}/join-requests/{request_id}/approve/."""

    role = serializers.ChoiceField(
        choices=OrganizationMember.Role.choices,
        default=OrganizationMember.Role.MEMBER,
        help_text="Role to assign to the new member (defaults to MEMBER).",
    )


class RejectJoinRequestSerializer(serializers.Serializer):
    """Validate POST /orgs/{id}/join-requests/{request_id}/reject/."""

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Optional reason for rejection (shared with the requester).",
    )
