from rest_framework import serializers

from ..models import Organization, OrganizationMember

# Re-export all input serializers unchanged.
from ..v1.serializers import (  # noqa: F401
    ApproveJoinRequestSerializer,
    CheckOrCreateOrganizationSerializer,
    CreateJoinRequestSerializer,
    InviteSerializer,
    JoinOrganizationSerializer,
    JoinRequestListSerializer,
    JoinRequestSerializer,
    RejectJoinRequestSerializer,
    UpdateMemberRoleSerializer,
)


class _UserInlineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.CharField(read_only=True)


class OrganizationSerializerV2(serializers.ModelSerializer):
    """
    v2 organisation representation.

    New fields vs v1
    ----------------
    ``member_count``  — active member count (requires ``Count`` annotation on queryset)
    ``updated_at``    — ISO 8601 timestamp of the last metadata change
    ``plan_limits``   — denormalised plan caps (e.g. max_members, max_posts)
    """

    member_count = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Organization
        fields = [
            # v1 fields (unchanged)
            "id",
            "name",
            "slug",
            "schema_name",
            "plan",
            "is_active",
            "created_at",
            # v2 additions
            "updated_at",
            "member_count",
            "plan_limits",
        ]
        read_only_fields = fields


class OrganizationMemberSerializerV2(serializers.ModelSerializer):
    """
    v2 member representation.

    New fields vs v1
    ----------------
    ``joined_at``        — semantic alias for ``created_at``
    ``invited_by_email`` — email of the person who sent the invitation; null for founding owner
    """

    user = _UserInlineSerializer(read_only=True)
    organization_id = serializers.UUIDField(read_only=True)
    joined_at = serializers.DateTimeField(source="created_at", read_only=True)
    invited_by_email = serializers.SerializerMethodField()

    def get_invited_by_email(self, obj: OrganizationMember) -> str | None:
        if obj.invited_by_id is None:
            return None
        return getattr(obj.invited_by, "email", None)

    class Meta:
        model = OrganizationMember
        fields = [
            # v1 fields (unchanged)
            "id",
            "user",
            "organization_id",
            "role",
            "is_active",
            "created_at",
            # v2 additions
            "joined_at",
            "invited_by_email",
        ]
        read_only_fields = fields


class OrganizationStatsSerializer(serializers.Serializer):
    """
    Response shape for GET /api/v2/orgs/{id}/stats/.

    All counts are live (not cached) so they always reflect current state.
    """

    org_id = serializers.UUIDField()
    org_name = serializers.CharField()
    plan = serializers.CharField()
    member_count = serializers.IntegerField()
    pending_join_requests = serializers.IntegerField()
    pending_invitations = serializers.IntegerField()
    plan_limits = serializers.DictField(child=serializers.IntegerField(allow_null=True))
