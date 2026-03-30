"""
Organizations — Models
========================
Organization is the tenant root. Every other model has org_id.
RLS on PostgreSQL enforces tenant isolation at the DB level.

Models:
  Organization       — the SaaS tenant (company, agency, or individual)
  OrganizationMember — join table: user ↔ org with a role
"""

import uuid

from django.conf import settings
from django.db import models


class Organization(models.Model):
    """
    Tenant root model.

    plan_limits is denormalized from settings.PLAN_LIMITS at creation /
    plan change so that limit checks are a single attribute read rather than
    a settings lookup + join.
    """

    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro ($29/mo)"
        BUSINESS = "business", "Business ($99/mo)"
        ENTERPRISE = "enterprise", "Enterprise (Custom)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=100)

    # Subscription
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    plan_limits = models.JSONField(default=dict)  # Denormalized limits

    # Billing (Stripe)
    billing_customer_id = models.CharField(max_length=100, blank=True)
    subscription_id = models.CharField(max_length=100, blank=True)

    # Status
    is_active = models.BooleanField(default=True)

    # Org-level settings (whitelabel, notification prefs, etc.)
    settings = models.JSONField(default=dict)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organizations"
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["billing_customer_id"]),
            models.Index(fields=["is_active", "plan"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.plan})"

    def get_limit(self, key: str):
        """Retrieve a specific plan limit value. Returns None for unlimited."""
        return self.plan_limits.get(key)

    def is_at_limit(self, key: str, current_count: int) -> bool:
        """Check if the org has reached a numeric plan limit."""
        limit = self.get_limit(key)
        if limit is None:
            return False  # None means unlimited
        return current_count >= limit

    def save(self, *args, **kwargs) -> None:
        # Auto-populate plan_limits when plan changes
        if not self.plan_limits or self._plan_changed():
            from django.conf import settings as django_settings

            self.plan_limits = django_settings.PLAN_LIMITS.get(self.plan, {})
        super().save(*args, **kwargs)

    def _plan_changed(self) -> bool:
        if not self.pk:
            return True
        try:
            old_plan = Organization.objects.filter(pk=self.pk).values_list("plan", flat=True)[0]
            return old_plan != self.plan
        except IndexError:
            return True


class OrganizationMember(models.Model):
    """
    Many-to-many between User and Organization with a role.

    Role hierarchy (descending privilege): owner > admin > editor > viewer.
    Enforced in permission classes; the DB stores the string value.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        EDITOR = "editor", "Editor"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_members",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    is_active = models.BooleanField(default=True)

    # Invite tracking
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_invitations",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    # Granular notification preferences per member
    notification_settings = models.JSONField(default=dict)

    class Meta:
        db_table = "organization_members"
        unique_together = [("organization", "user")]
        indexes = [
            models.Index(fields=["organization", "role"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.organization} [{self.role}]"
