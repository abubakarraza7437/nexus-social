"""
Auth Core v2 — Serializers
============================
Extends v1 serializers with richer response shapes.

Changes vs v1
-------------
``UserProfileSerializer`` (NEW)
    Read-only user profile embedded in login and signup responses.
    Eliminates the extra /me round-trip v1 clients make after login.

All input serializers (SignupSerializer, ForgotPasswordSerializer, etc.)
are re-exported unchanged — the request contracts are identical in v1 and v2.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

# Re-export all v1 input serializers unchanged.
from ..v1.serializers import (  # noqa: F401
    CustomTokenObtainSerializer,
    ForgotPasswordSerializer,
    LogoutSerializer,
    ResetPasswordSerializer,
    SignupSerializer,
)

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Read-only user profile embedded in v2 auth responses.

    Fields beyond the JWT claims
    -----------------------------
    ``avatar_url``   — profile picture URL (empty string when not set)
    ``is_verified``  — whether the user has confirmed their email
    ``mfa_enabled``  — whether TOTP MFA is configured

    Embedding these in the JSON body lets clients avoid decoding the JWT
    on the client side immediately after login / signup.
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


# ---------------------------------------------------------------------------
# Schema-documentation serializers (used by drf-spectacular only)
# ---------------------------------------------------------------------------

class LoginResponseSerializer(serializers.Serializer):
    """Documents the v2 login response shape for OpenAPI schema generation."""

    access = serializers.CharField(help_text="Short-lived JWT access token (15 min).")
    refresh = serializers.CharField(help_text="Rotating JWT refresh token (7 days).")
    user = UserProfileSerializer(help_text="Authenticated user's profile.")


class SignupResponseSerializer(serializers.Serializer):
    """Documents the v2 signup response shape for OpenAPI schema generation."""

    detail = serializers.CharField()
    user = UserProfileSerializer()
