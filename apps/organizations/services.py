"""
Organizations — Services
========================
Business-logic functions that operate on Organisation-related models,
keeping views thin and logic testable.
"""
import logging
import re
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    Domain,
    JoinRequest,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Invitation Services
# ---------------------------------------------------------------------------

def create_invitation(
    org,
    invited_by,
    email: str,
    role: str,
) -> OrganizationInvitation:
    """
    Create (or re-create) an invitation for *email* to join *org* as *role*.

    Any existing **pending** (is_used=False) invitations for the same
    email + org pair are invalidated first so only one active token exists
    at a time.

    Args:
        org:        Organization instance.
        invited_by: User instance issuing the invitation.
        email:      Email address of the invitee.
        role:       OrganizationMember.Role value string.

    Returns:
        The newly created :class:`~apps.organizations.models.OrganizationInvitation`.
    """
    # Invalidate any prior pending invitations for this email+org.
    OrganizationInvitation.objects.filter(
        organization=org,
        email=email,
        is_used=False,
    ).update(is_used=True)

    invitation = OrganizationInvitation.objects.create(
        organization=org,
        email=email,
        role=role,
        invited_by=invited_by,
    )
    return invitation


# ---------------------------------------------------------------------------
# Organization Onboarding Services
# ---------------------------------------------------------------------------

def check_organization_exists(name: str) -> Optional[Organization]:
    """
    Check if an organization with the given name exists (case-insensitive).

    Args:
        name: Organization name to check.

    Returns:
        Organization instance if found, None otherwise.
    """
    return Organization.objects.filter(
        name__iexact=name.strip(),
        is_active=True,
    ).first()


def generate_unique_slug(name: str) -> str:
    """
    Generate a unique slug from the organization name.

    Handles collisions by appending a numeric suffix.

    Args:
        name: Organization name.

    Returns:
        Unique slug string.
    """
    base_slug = slugify(name)[:90]  # Leave room for suffix

    # Ensure slug is not empty
    if not base_slug:
        base_slug = "org"

    slug = base_slug
    counter = 1

    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def generate_schema_name(slug: str) -> str:
    """
    Generate a PostgreSQL-safe schema name from the slug.

    PostgreSQL schema names must:
    - Start with a letter or underscore
    - Contain only letters, digits, and underscores
    - Be lowercase

    Args:
        slug: Organization slug.

    Returns:
        Valid PostgreSQL schema name.
    """
    # Replace hyphens with underscores, remove invalid chars
    schema_name = re.sub(r"[^a-z0-9_]", "_", slug.lower())

    # Ensure it starts with a letter
    if schema_name and not schema_name[0].isalpha():
        schema_name = f"org_{schema_name}"

    # Ensure uniqueness
    base_schema = schema_name[:50]  # PostgreSQL limit is 63
    schema_name = base_schema
    counter = 1

    while Organization.objects.filter(schema_name=schema_name).exists():
        schema_name = f"{base_schema}_{counter}"
        counter += 1

    return schema_name


@transaction.atomic
def create_organization_with_owner(
    name: str,
    owner_user,
    plan: str = Organization.Plan.FREE,
) -> tuple[Organization, OrganizationMember]:
    """
    Create a new Organization with the given user as OWNER.

    This function:
    1. Creates the Organization (TenantMixin auto-creates the schema)
    2. Creates the Domain entry (required by django-tenants)
    3. Creates the OrganizationMember with role=OWNER

    Args:
        name: Organization name.
        owner_user: User instance to become the owner.
        plan: Initial plan (defaults to FREE).

    Returns:
        Tuple of (Organization, OrganizationMember).

    Raises:
        ValueError: If organization name already exists.
    """
    # Double-check uniqueness (case-insensitive)
    if check_organization_exists(name):
        raise ValueError(f"Organization with name '{name}' already exists.")

    # Generate unique identifiers
    slug = generate_unique_slug(name)
    schema_name = generate_schema_name(slug)

    # Create the organization (TenantMixin.save() creates the schema)
    org = Organization.objects.create(
        name=name.strip(),
        slug=slug,
        schema_name=schema_name,
        plan=plan,
    )

    # Create the primary domain (required by django-tenants)
    # Format: {slug}.{base_domain}
    base_domain = getattr(settings, "TENANT_BASE_DOMAIN", "localhost")
    domain_name = f"{slug}.{base_domain}"

    Domain.objects.create(
        domain=domain_name,
        tenant=org,
        is_primary=True,
    )

    # Create the owner membership
    membership = OrganizationMember.objects.create(
        organization=org,
        user=owner_user,
        role=OrganizationMember.Role.OWNER,
    )

    logger.info(
        "Created organization '%s' (schema=%s) with owner %s",
        org.name,
        org.schema_name,
        owner_user.email,
    )

    return org, membership


# ---------------------------------------------------------------------------
# Join Request Services
# ---------------------------------------------------------------------------

def create_join_request(
    user,
    organization: Organization,
    message: str = "",
) -> JoinRequest:
    """
    Create a join request for a user to join an organization.

    Args:
        user: User requesting to join.
        organization: Target organization.
        message: Optional message from the user.

    Returns:
        The created JoinRequest instance.

    Raises:
        ValueError: If user is already a member or has a pending request.
    """
    # Check if already a member
    if OrganizationMember.objects.filter(
        organization=organization,
        user=user,
        is_active=True,
    ).exists():
        raise ValueError("User is already a member of this organization.")

    # Check for existing pending request
    existing_request = JoinRequest.objects.filter(
        organization=organization,
        user=user,
        status=JoinRequest.Status.PENDING,
    ).first()

    if existing_request and existing_request.is_pending:
        raise ValueError("User already has a pending request for this organization.")

    # Create the join request
    join_request = JoinRequest.objects.create(
        user=user,
        organization=organization,
        message=message,
        status=JoinRequest.Status.PENDING,
    )

    logger.info(
        "Created join request %s: user=%s, org=%s",
        join_request.id,
        user.email,
        organization.name,
    )

    return join_request


def get_organization_admins(organization: Organization):
    """
    Get all OWNER and ADMIN members of an organization.

    Args:
        organization: Target organization.

    Returns:
        QuerySet of OrganizationMember instances with OWNER or ADMIN role.
    """
    return OrganizationMember.objects.filter(
        organization=organization,
        role__in=[OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN],
        is_active=True,
    ).select_related("user")


@transaction.atomic
def approve_join_request(
    join_request: JoinRequest,
    reviewer,
    role: str = OrganizationMember.Role.MEMBER,
) -> OrganizationMember:
    """
    Approve a join request and create the membership.

    Args:
        join_request: The JoinRequest to approve.
        reviewer: User approving the request (must be OWNER/ADMIN).
        role: Role to assign (defaults to MEMBER for least privilege).

    Returns:
        The created OrganizationMember instance.

    Raises:
        ValueError: If request is not pending or already processed.
    """
    # Re-fetch with a row lock so concurrent approvals don't both pass the
    # status check and create a duplicate OrganizationMember.
    join_request = JoinRequest.objects.select_for_update().get(pk=join_request.pk)

    if join_request.status != JoinRequest.Status.PENDING:
        raise ValueError(f"Join request is not pending (status={join_request.status}).")

    if join_request.is_expired:
        join_request.status = JoinRequest.Status.EXPIRED
        join_request.save(update_fields=["status", "updated_at"])
        raise ValueError("Join request has expired.")

    # Create the membership
    membership = OrganizationMember.objects.create(
        organization=join_request.organization,
        user=join_request.user,
        role=role,
        invited_by=reviewer,
    )

    # Update the join request
    join_request.status = JoinRequest.Status.APPROVED
    join_request.reviewed_by = reviewer
    join_request.reviewed_at = timezone.now()
    join_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    logger.info(
        "Approved join request %s: user=%s joined org=%s as %s",
        join_request.id,
        join_request.user.email,
        join_request.organization.name,
        role,
    )

    return membership


@transaction.atomic
def reject_join_request(
    join_request: JoinRequest,
    reviewer,
    reason: str = "",
) -> JoinRequest:
    """
    Reject a join request.

    Args:
        join_request: The JoinRequest to reject.
        reviewer: User rejecting the request (must be OWNER/ADMIN).
        reason: Optional reason for rejection.

    Returns:
        The updated JoinRequest instance.

    Raises:
        ValueError: If request is not pending.
    """
    if join_request.status != JoinRequest.Status.PENDING:
        raise ValueError(f"Join request is not pending (status={join_request.status}).")

    join_request.status = JoinRequest.Status.REJECTED
    join_request.reviewed_by = reviewer
    join_request.reviewed_at = timezone.now()
    join_request.rejection_reason = reason
    join_request.save(update_fields=[
        "status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"
    ])

    logger.info(
        "Rejected join request %s: user=%s, org=%s, reason=%s",
        join_request.id,
        join_request.user.email,
        join_request.organization.name,
        reason or "(none)",
    )

    return join_request


# ---------------------------------------------------------------------------
# Notification Services (Mock)
# ---------------------------------------------------------------------------

def notify_admins_of_join_request(join_request: JoinRequest) -> None:
    """
    Email every OWNER/ADMIN in the organization about a new join request.

    Args:
        join_request: The new JoinRequest instance.
    """
    from apps.auth_core.services import _send_email

    admins = get_organization_admins(join_request.organization)
    requester_email = join_request.user.email
    requester_name = join_request.user.name or requester_email
    org_name = join_request.organization.name

    from django.conf import settings as django_settings
    frontend_url = getattr(django_settings, "FRONTEND_URL", "http://localhost:3000")
    review_url = (
        f"{frontend_url}/orgs/{join_request.organization.id}"
        f"/join-requests/{join_request.id}"
    )

    for admin_member in admins:
        html = (
            f"<p>Hi {admin_member.user.name or admin_member.user.email},</p>"
            f"<p><strong>{requester_name}</strong> ({requester_email}) has requested "
            f"to join <strong>{org_name}</strong>.</p>"
            + (
                f"<blockquote>{join_request.message}</blockquote>"
                if join_request.message
                else ""
            )
            + f'<p><a href="{review_url}">Review the request</a></p>'
        )
        text = (
            f"Hi {admin_member.user.name or admin_member.user.email},\n\n"
            f"{requester_name} ({requester_email}) has requested to join {org_name}.\n"
            + (f"\nMessage: {join_request.message}\n" if join_request.message else "")
            + f"\nReview here: {review_url}"
        )
        _send_email(
            admin_member.user.email,
            f"New join request for {org_name}",
            html,
            text,
        )


def notify_user_of_request_decision(
    join_request: JoinRequest,
    approved: bool,
) -> None:
    """
    Email the requesting user about the outcome of their join request.

    Args:
        join_request: The processed JoinRequest instance.
        approved: Whether the request was approved.
    """
    from apps.auth_core.services import _send_email

    org_name = join_request.organization.name
    user = join_request.user
    from django.conf import settings as django_settings
    frontend_url = getattr(django_settings, "FRONTEND_URL", "http://localhost:3000")

    if approved:
        subject = f"You've been approved to join {org_name}"
        html = (
            f"<p>Hi {user.name or user.email},</p>"
            f"<p>Great news! Your request to join <strong>{org_name}</strong> "
            f"has been <strong>approved</strong>.</p>"
            f'<p><a href="{frontend_url}">Open SocialOS</a></p>'
        )
        text = (
            f"Hi {user.name or user.email},\n\n"
            f"Your request to join {org_name} has been approved.\n\n"
            f"Log in here: {frontend_url}"
        )
    else:
        subject = f"Your request to join {org_name} was not approved"
        reason_line = (
            f"<p>Reason: {join_request.rejection_reason}</p>"
            if join_request.rejection_reason
            else ""
        )
        html = (
            f"<p>Hi {user.name or user.email},</p>"
            f"<p>Your request to join <strong>{org_name}</strong> was "
            f"<strong>not approved</strong>.</p>"
            + reason_line
        )
        text = (
            f"Hi {user.name or user.email},\n\n"
            f"Your request to join {org_name} was not approved.\n"
            + (f"Reason: {join_request.rejection_reason}" if join_request.rejection_reason else "")
        )

    _send_email(user.email, subject, html, text)
