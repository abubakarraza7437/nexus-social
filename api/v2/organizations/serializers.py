"""
Organizations v2 — Serializers
================================
Extends v1 serializers with richer read payloads.

Changes vs v1
-------------
``OrganizationSerializerV2``
    Adds ``member_count`` (annotated integer) and ``updated_at`` to the
    organisation representation.  ``plan_limits`` is also exposed so clients
    can display plan caps without a separate settings call.

    Removed fields: none (fully backward-compatible field set).

``OrganizationMemberSerializerV2``
    Adds ``invited_by_email`` (nullable — the email address of the person who
    sent the invitation) and renames the join timestamp field to ``joined_at``
    for clearer semantics (``created_at`` is preserved as an alias for clients
    that already read it).

``OrganizationStatsSerializer`` (NEW)
    Response shape for the new ``GET /api/v2/orgs/{id}/stats/`` endpoint.

All write/input serializers (``InviteSerializer``, ``JoinOrganizationSerializer``,
etc.) are re-exported unchanged — the input contracts are identical in v1 and v2.
"""
from rest_framework import serializers

from apps.organizations.models import Organization, OrganizationMember

# Re-export all input serializers unchanged so v2 views only import from here.
from apps.organizations.serializers import (  # noqa: F401
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


# ---------------------------------------------------------------------------
# Inline user representation (same as v1 — shared via composition)
# ---------------------------------------------------------------------------

class _UserInlineSerializer(serializers.Serializer):
    """Minimal read-only user representation embedded in member payloads."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.CharField(read_only=True)


# ---------------------------------------------------------------------------
# Organization (v2)
# ---------------------------------------------------------------------------

class OrganizationSerializerV2(serializers.ModelSerializer):
    """
    v2 organisation representation.

    New fields vs v1
    ----------------
    ``member_count``  int   Active member count (requires ``Count`` annotation
                            on the queryset — see ``OrganizationListViewV2``).
    ``updated_at``    str   ISO 8601 timestamp of the last metadata update.
    ``plan_limits``   obj   Denormalised snapshot of the plan's resource caps
                            (e.g. ``max_members``, ``max_posts``).
    """

    # Populated by a ``Count`` annotation on the queryset.  Falls back to None
    # when the queryset is not annotated (e.g. in tests that pass a plain ORM
    # object) — serializer will return null rather than throwing AttributeError.
    member_count = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Organization
        fields = [
            # --- v1 fields (unchanged) ---
            "id",
            "name",
            "slug",
            "schema_name",
            "plan",
            "is_active",
            "created_at",
            # --- v2 additions ---
            "updated_at",
            "member_count",
            "plan_limits",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# OrganizationMember (v2)
# ---------------------------------------------------------------------------

class OrganizationMemberSerializerV2(serializers.ModelSerializer):
    """
    v2 member representation.

    New fields vs v1
    ----------------
    ``joined_at``       str          Alias for ``created_at`` with clearer semantics.
    ``invited_by_email`` str | null  Email of the person who sent the invitation.
                                     Null for the founding owner (no invitation sent).
    """

    user = _UserInlineSerializer(read_only=True)
    organization_id = serializers.UUIDField(read_only=True)

    # Semantic alias for created_at — keeps backward compat (created_at still present).
    joined_at = serializers.DateTimeField(source="created_at", read_only=True)

    # Null for the founding owner; populated otherwise.
    invited_by_email = serializers.SerializerMethodField()

    def get_invited_by_email(self, obj: OrganizationMember) -> str | None:
        if obj.invited_by_id is None:
            return None
        return getattr(obj.invited_by, "email", None)

    class Meta:
        model = OrganizationMember
        fields = [
            # --- v1 fields (unchanged) ---
            "id",
            "user",
            "organization_id",
            "role",
            "is_active",
            "created_at",
            # --- v2 additions ---
            "joined_at",
            "invited_by_email",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Organization Stats (v2 — new endpoint)
# ---------------------------------------------------------------------------

class OrganizationStatsSerializer(serializers.Serializer):
    """
    Response shape for ``GET /api/v2/orgs/{id}/stats/``.

    Aggregated at request time — not stored — so it always reflects live data.
    """

    org_id = serializers.UUIDField()
    org_name = serializers.CharField()
    plan = serializers.CharField()
    member_count = serializers.IntegerField()
    pending_join_requests = serializers.IntegerField()
    pending_invitations = serializers.IntegerField()
    plan_limits = serializers.DictField(child=serializers.IntegerField(allow_null=True))
