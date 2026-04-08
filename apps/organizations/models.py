"""
Organizations — Models
======================
Organization is the django-tenants tenant root. Each org maps 1-to-1 with
an isolated PostgreSQL schema.

Models (all in the public schema via SHARED_APPS):
  Organization          — TenantMixin subclass; the SaaS tenant
  Domain                — DomainMixin subclass; maps hostnames → tenant
  OrganizationMember    — join table: user ↔ organization with a role
  OrganizationInvitation — pending email invitations to join an org
"""
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
    """
    SaaS tenant — each Organization maps to an isolated PostgreSQL schema.

    TenantMixin contributes:
      • schema_name     — unique CharField (the PostgreSQL schema identifier)
      • auto_create_schema — class attr; when True, TenantMixin.save() creates
                            the schema automatically on first save.
      • Schema lifecycle helpers (create_schema, drop_schema, etc.)

    plan_limits is denormalized from settings.PLAN_LIMITS at creation /
    plan change so limit checks are a single attribute read with no joins.
    """

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

    # ------------------------------------------------------------------
    # save() — auto-populate plan_limits; then delegate to TenantMixin
    # (which in turn calls models.Model.save() and creates the schema).
    # ------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Domain  (required by django-tenants; referenced via TENANT_DOMAIN_MODEL)
# ---------------------------------------------------------------------------

class Domain(DomainMixin):
    """
    Maps a domain / subdomain to an Organization tenant.

    DomainMixin contributes:
      • domain     — unique CharField (the hostname, e.g. "acme.socialos.io")
      • tenant     — ForeignKey → TENANT_MODEL
      • is_primary — BooleanField (True for the canonical domain)
    """

    class Meta:
        db_table = "organization_domains"
        verbose_name = "Domain"
        verbose_name_plural = "Domains"

    def __str__(self) -> str:
        return self.domain


# ---------------------------------------------------------------------------
# OrganizationMember  (user ↔ org join table)
# ---------------------------------------------------------------------------

class OrganizationMember(models.Model):
    """
    Many-to-many between User ↔ Organization with a role.

    Role hierarchy (descending privilege): OWNER > ADMIN > MEMBER.
    Enforced in permission classes; the DB stores the string value.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

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
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
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


# ---------------------------------------------------------------------------
# JoinRequest  (user-initiated request to join an existing org)
# ---------------------------------------------------------------------------

class JoinRequest(models.Model):
    """
    Represents a user-initiated request to join an existing Organization.

    Security model (Slack/Notion-style):
      - Users cannot auto-join organizations based on name/domain.
      - A JoinRequest must be explicitly approved by an OWNER or ADMIN.
      - Only one pending request per user+org pair is allowed.

    Lifecycle:
      1. User submits org name → org exists → user confirms join request.
      2. JoinRequest created with status=PENDING.
      3. Notification sent to org OWNER/ADMIN.
      4. OWNER/ADMIN approves → OrganizationMember created, status=APPROVED.
         OR OWNER/ADMIN rejects → status=REJECTED.

    Requests expire after 30 days if not acted upon.
    """

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


# ---------------------------------------------------------------------------
# Invitation expiry callable — module-level so it is picklable for migrations.
# ---------------------------------------------------------------------------

def _invitation_expiry():
    return timezone.now() + timedelta(days=7)


# ---------------------------------------------------------------------------
# OrganizationInvitation  (pending email invite to join an org)
# ---------------------------------------------------------------------------

class OrganizationInvitation(models.Model):
    """
    Represents a pending invitation for a specific email address to join an
    Organization with a given role.

    Lifecycle:
      1. OWNER / ADMIN calls invite endpoint → invitation created, email sent.
      2. Invitee registers (or logs in) and calls join endpoint with token.
      3. OrganizationMember is created; is_used flipped to True.

    Tokens expire after 7 days.  A new invitation for the same email+org
    invalidates all prior pending invitations for that pair.
    """

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
        default=OrganizationMember.Role.MEMBER,
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
