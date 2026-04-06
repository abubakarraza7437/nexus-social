"""
Auth Core v1 — Serializers
============================
Moved here from apps/auth_core/serializers.py (the root file is now a
backward-compat shim that re-exports everything from this module).

No logic changes from the original — this is the canonical v1 contract.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    validate_password as django_validate_password,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import Token

User = get_user_model()


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


class SignupSerializer(serializers.Serializer):
    """Validate registration input before creating a user."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10)
    name = serializers.CharField(max_length=255)

    def validate_email(self, value: str) -> str:
        normalized = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError(
                "This email is already registered. Please sign in instead."
            )
        return normalized

    def validate_password(self, value: str) -> str:
        try:
            django_validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    """Accept an email address for the password-reset flow."""

    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    """Validate the reset token + new password."""

    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=10)

    def validate_password(self, value: str) -> str:
        try:
            django_validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class LogoutSerializer(serializers.Serializer):
    """Accept a refresh token for blacklisting."""

    refresh = serializers.CharField()
