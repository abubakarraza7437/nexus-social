"""
Auth v2 — Serializers
======================
Extends v1 auth serializers with richer payloads.

Changes vs v1
-------------
``UserProfileSerializer`` (NEW)
    A concise, read-only user representation embedded directly in login and
    signup responses.  Eliminates the extra ``/me`` round-trip that v1 clients
    perform immediately after authentication.

``SignupSerializer``
    Re-exported unchanged from v1 — input contract is identical.

``LoginResponseSerializer`` (documentation-only)
    Describes the shape of the v2 login response for drf-spectacular schema
    generation.  Not used for validation.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

# Re-export unchanged v1 input serializers so v2 views only need to import
# from this module.
from apps.auth_core.serializers import (  # noqa: F401 — intentional re-export
    ForgotPasswordSerializer,
    LogoutSerializer,
    ResetPasswordSerializer,
    SignupSerializer,
)

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Read-only user profile embedded in v2 auth responses.

    Added fields vs v1 JWT payload
    --------------------------------
    ``avatar_url``   — profile picture URL (empty string when not set)
    ``is_verified``  — whether the user has verified their email address
    ``mfa_enabled``  — whether the user has TOTP MFA configured

    These fields are already present in the JWT token claims (added by
    ``CustomTokenObtainSerializer``), but embedding them in the JSON response
    body lets clients avoid decoding the JWT on the client side.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "avatar_url",
            "mfa_enabled",
            "is_verified",
        ]
        read_only_fields = fields


class LoginResponseSerializer(serializers.Serializer):
    """
    Schema-documentation serializer for the v2 login response.

    Not used for validation — only referenced by drf-spectacular via
    ``@extend_schema(responses=LoginResponseSerializer)`` in the view.
    """

    access = serializers.CharField(help_text="Short-lived JWT access token (15 min).")
    refresh = serializers.CharField(help_text="Rotating JWT refresh token (7 days).")
    user = UserProfileSerializer(help_text="Authenticated user's profile.")


class SignupResponseSerializer(serializers.Serializer):
    """Schema-documentation serializer for the v2 signup response."""

    detail = serializers.CharField()
    user = UserProfileSerializer()
