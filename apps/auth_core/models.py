"""
Auth Core — Models
==================
Covers:
  User                    — custom user model (public schema)
  EmailVerificationToken  — single-use email verification token (public schema)
  PasswordResetToken      — single-use password reset token (public schema)

All three live in the shared (public) PostgreSQL schema and are therefore
listed under SHARED_APPS in settings.
"""
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager):
    """Manager that uses email instead of username."""

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":
        if not email:
            raise ValueError("Email address is required.")
        email = self.normalize_email(email)
        user: User = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    SocialOS platform user — lives in the public schema, shared across all tenants.

    Authentication is email + password.  JWT tokens carry `org` and `role`
    claims embedded by CustomTokenObtainSerializer so views can enforce
    RBAC without a DB round-trip per request.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)

    # Account status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    # MFA — TOTP (e.g. Google Authenticator)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)  # Base32-encoded TOTP secret

    # Timestamps
    date_joined = models.DateTimeField(default=timezone.now)
    last_login_at = models.DateTimeField(null=True, blank=True)

    # Locale
    timezone = models.CharField(max_length=100, default="UTC")
    locale = models.CharField(max_length=10, default="en")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password are enough for createsuperuser

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_active", "is_staff"]),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0]

    @property
    def active_membership(self):
        """Return the user's most recently joined active org membership."""
        return (
            self.organization_members  # type: ignore[attr-defined]
            .filter(is_active=True)
            .select_related("organization")
            .order_by("-created_at")
            .first()
        )


# ---------------------------------------------------------------------------
# Token expiry callables — module-level so they are picklable for migrations.
# ---------------------------------------------------------------------------

def _email_token_expiry():
    return timezone.now() + timedelta(hours=24)


def _reset_token_expiry():
    return timezone.now() + timedelta(hours=1)


# ---------------------------------------------------------------------------
# EmailVerificationToken
# ---------------------------------------------------------------------------

class EmailVerificationToken(models.Model):
    """
    Single-use token emailed to a user to confirm address ownership.
    Expires after 24 hours.

    Lookup path: token (indexed, unique) → validate is_used + expires_at → mark used.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "auth_core.User",
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    # secrets.token_urlsafe() → 43-char URL-safe base64 string (256-bit entropy)
    token = models.CharField(
        max_length=64,
        unique=True,
        default=secrets.token_urlsafe,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_email_token_expiry)
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "email_verification_tokens"
        verbose_name = "Email Verification Token"
        verbose_name_plural = "Email Verification Tokens"
        indexes = [
            models.Index(fields=["token"], name="email_ver_token_idx"),
            models.Index(fields=["user", "is_used"], name="email_ver_user_used_idx"),
        ]

    def __str__(self) -> str:
        return f"EmailVerificationToken(user={self.user_id}, used={self.is_used})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired


# ---------------------------------------------------------------------------
# PasswordResetToken
# ---------------------------------------------------------------------------

class PasswordResetToken(models.Model):
    """
    Single-use token for password reset flows.
    Expires after 1 hour.

    Lookup path: token (indexed, unique) → validate is_used + expires_at → mark used.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "auth_core.User",
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        default=secrets.token_urlsafe,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_reset_token_expiry)
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "password_reset_tokens"
        verbose_name = "Password Reset Token"
        verbose_name_plural = "Password Reset Tokens"
        indexes = [
            models.Index(fields=["token"], name="pwd_reset_token_idx"),
            models.Index(fields=["user", "is_used"], name="pwd_reset_user_used_idx"),
        ]

    def __str__(self) -> str:
        return f"PasswordResetToken(user={self.user_id}, used={self.is_used})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired
