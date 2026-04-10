import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django_tenants.models import DomainMixin, TenantMixin

from apps.organizations.schemas import PlanLimits


# ---------------------------------------------------------------------------
# Organization  (tenant model)
# ---------------------------------------------------------------------------

class Organization(TenantMixin):

    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        BUSINESS = "business", "Business"
        ENTERPRISE = "enterprise", "Enterprise (Custom)"

    # UUID PK — TenantMixin does not define one, so we declare it explicitly.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    # slug: human-readable URL / display identifier (e.g. "acme-corp").
    # schema_name (from TenantMixin) is the PostgreSQL schema identifier and
    # must follow PostgreSQL naming rules (lowercase, no hyphens).
    slug = models.SlugField(unique=True, max_length=100)

    # Subscription
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    plan_limits = models.JSONField(default=dict)  # Denormalized snapshot of PLAN_LIMITS

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

    # TenantMixin: create the PostgreSQL schema on first save.
    auto_create_schema = True

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

    # ------------------------------------------------------------------
    # Plan limit helpers
    # ------------------------------------------------------------------

    def get_limit(self, key: str):
        """Retrieve a specific plan limit. Returns None for unlimited."""
        return self.plan_limits.get(key)

    def is_at_limit(self, key: str, current_count: int) -> bool:
        """True if the org has hit a numeric plan ceiling."""
        limit = self.get_limit(key)
        if limit is None:
            return False  # None → unlimited
        return current_count >= limit

    def get_plan_limits(self) -> PlanLimits:
        """Return the current plan limits as a validated Pydantic model."""
        return PlanLimits.model_validate(self.plan_limits)

    def save(self, *args, **kwargs) -> None:
        if not self.plan_limits or self._plan_changed():
            raw = settings.PLAN_LIMITS.get(self.plan, {})
            self.plan_limits = PlanLimits.model_validate(raw).model_dump(mode="json")
        super().save(*args, **kwargs)

    def _plan_changed(self) -> bool:
        if not self.pk:
            return True
        try:
            return (
                Organization.objects.filter(pk=self.pk)
                .values_list("plan", flat=True)[0] != self.plan
            )
        except IndexError:
            return True


class Domain(DomainMixin):

    class Meta:
        db_table = "organization_domains"
        verbose_name = "Domain"
        verbose_name_plural = "Domains"

    def __str__(self) -> str:
        return self.domain


class OrganizationMember(models.Model):

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
    created_at = models.DateTimeField(auto_now_add=True)

    # Per-member notification preferences
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


class JoinRequest(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="join_requests",
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="join_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    # Optional message from the user explaining why they want to join
    message = models.TextField(blank=True, max_length=500)

    # Tracking who processed the request
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_join_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, max_length=500)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(default=None, null=True, blank=True)

    class Meta:
        db_table = "organization_join_requests"
        # Only one pending request per user+org
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=models.Q(status="pending"),
                name="unique_pending_join_request",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"JoinRequest(user={self.user_id}, org={self.organization_id}, "
            f"status={self.status})"
        )

    def save(self, *args, **kwargs):
        # Set expiry on creation (30 days)
        if not self.pk and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING and not self.is_expired


def _invitation_expiry():
    return timezone.now() + timedelta(days=7)


class OrganizationInvitation(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=20,
        choices=OrganizationMember.Role.choices,
        default=OrganizationMember.Role.VIEWER,
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        default=secrets.token_urlsafe,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_org_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_invitation_expiry)
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "organization_invitations"
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["organization", "email"]),
            models.Index(fields=["organization", "is_used"]),
        ]

    def __str__(self) -> str:
        return (
            f"OrganizationInvitation(org={self.organization_id}, "
            f"email={self.email}, role={self.role}, used={self.is_used})"
        )

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired
