"""
Auth Core — User Model
=======================
Custom user model with:
- UUID primary key
- Email as the login identifier (no username)
- MFA (TOTP) support fields
- Soft timestamps
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


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
        extra_fields.setdefault("is_email_verified", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    SocialOS platform user.

    Authentication is email + password.  JWT tokens carry `org` and `role`
    claims embedded by CustomTokenObtainSerializer so views can enforce
    RBAC without a DB round-trip per request.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)

    # Account status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    # MFA — TOTP (e.g. Google Authenticator)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)  # Base32-encoded TOTP secret

    # Timestamps
    date_joined = models.DateTimeField(default=timezone.now)
    last_login_at = models.DateTimeField(null=True, blank=True)

    # Metadata
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
        return self.full_name or self.email.split("@")[0]

    @property
    def active_membership(self):
        """Return the user's first active org membership.

        Returns the most recently joined active membership.
        """
        return (
            self.organization_members.filter(is_active=True)  # type: ignore[attr-defined]
            .select_related("organization")
            .order_by("-joined_at")
            .first()
        )
