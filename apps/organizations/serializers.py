"""
Organizations — Serializers
============================
Covers Organisation read, member management, and invitation flows.
"""
from rest_framework import serializers

from .models import Organization, OrganizationMember


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
