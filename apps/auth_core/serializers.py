"""
Auth Core — Serializers
========================
CustomTokenObtainSerializer: embeds org_id + role in the JWT payload so
downstream services can enforce RBAC without a DB round-trip.
"""

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import Token


class CustomTokenObtainSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT pair serializer to add organization context.

    Token payload additions:
      - org:  str  → active organization UUID
      - role: str  → member role in that org (owner/admin/editor/viewer)
      - name: str  → user display name (convenience for frontend)
    """

    @classmethod
    def get_token(cls, user) -> Token:
        token = super().get_token(user)

        membership = user.active_membership
        if membership:
            token["org"] = str(membership.organization_id)
            token["role"] = membership.role
        else:
            token["org"] = None
            token["role"] = None

        token["name"] = user.display_name
        token["email"] = user.email
        token["mfa_enabled"] = user.mfa_enabled

        return token
