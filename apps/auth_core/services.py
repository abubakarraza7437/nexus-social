"""
Auth Core — Services
====================
Business-logic functions for user registration, organisation bootstrapping,
and transactional email dispatch via Gmail SMTP.
"""
import logging
import re
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _schema_name_from_base(base: str) -> str:
    """
    Derive a PostgreSQL-safe schema identifier from *base*.

    Steps:
      1. Lowercase, keep only [a-z0-9_].
      2. Truncate to 20 characters.
      3. Append "_" + 8 hex chars (uuid4 fragment) for uniqueness.
      4. Ensure the result starts with a letter (prefix "org" if needed).
    """
    sanitized = re.sub(r"[^a-z0-9_]", "", base.lower())[:20]
    suffix = uuid.uuid4().hex[:8]
    schema = f"{sanitized}_{suffix}"
    if not schema[0].isalpha():
        schema = f"org{schema}"
    return schema


def _unique_slug(base: str) -> str:
    """
    Produce a URL-safe slug that is not already used by any Organization.

    Steps:
      1. Slugify *base* (replace non-alphanumeric runs with "-"), max 40 chars.
      2. Append "-" + 6 hex chars.
      3. Loop until the result is absent from Organization.objects.
    """
    from apps.organizations.models import Organization  # avoid circular at module load

    from django.utils.text import slugify

    base_slug = slugify(base)[:40]
    while True:
        candidate = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        if not Organization.objects.filter(slug=candidate).exists():
            return candidate


# ---------------------------------------------------------------------------
# Core service: register user + bootstrap personal organisation
# ---------------------------------------------------------------------------

@transaction.atomic
def create_user(validated_data: dict) -> User:
    """
    Create a User and dispatch the email-verification token.

    This is the standard signup path. Organisation creation is deferred to
    the post-signup onboarding flow (POST /api/v1/orgs/check-or-create/).

    Args:
        validated_data: cleaned dict with keys ``email``, ``password``, ``name``.

    Returns:
        The newly-created :class:`~apps.auth_core.models.User` instance.
    """
    from apps.auth_core.models import EmailVerificationToken

    email: str = validated_data["email"]
    password: str = validated_data["password"]
    name: str = validated_data.get("name", "")

    user = User.objects.create_user(email=email, password=password, name=name)

    ev_token = EmailVerificationToken.objects.create(user=user)
    send_verification_email(user, ev_token.token)

    return user


@transaction.atomic
def create_user_with_organization(validated_data: dict) -> User:
    """
    Atomically create a User and bootstrap a personal Organisation.

    Retained for admin / internal tooling. The public signup flow uses
    :func:`create_user` instead, deferring org creation to onboarding.

    Args:
        validated_data: cleaned dict with keys ``email``, ``password``, ``name``.

    Returns:
        The newly-created :class:`~apps.auth_core.models.User` instance.
    """
    from apps.auth_core.models import EmailVerificationToken
    from apps.organizations.models import Domain, Organization, OrganizationMember

    email: str = validated_data["email"]
    password: str = validated_data["password"]
    name: str = validated_data.get("name", "")

    # 1. Create user.
    user = User.objects.create_user(email=email, password=password, name=name)

    # 2. Email verification token.
    ev_token = EmailVerificationToken.objects.create(user=user)
    send_verification_email(user, ev_token.token)

    # 3. Derive org name.
    if name.strip():
        org_name = f"{name.strip()}'s Workspace"
    else:
        email_local = email.split("@")[0]
        org_name = f"{email_local}'s Workspace"

    # 4. Create Organisation — TenantMixin.save() creates the PG schema.
    schema_name = _schema_name_from_base(name.strip() or email.split("@")[0])
    slug = _unique_slug(name.strip() or email.split("@")[0])

    org = Organization(
        name=org_name,
        slug=slug,
        schema_name=schema_name,
    )
    org.save()  # triggers schema creation via TenantMixin

    # 5. Create primary Domain.
    base_domain = getattr(settings, "TENANT_BASE_DOMAIN", "localhost")
    domain_value = f"{schema_name}.{base_domain}"
    Domain.objects.create(
        domain=domain_value,
        tenant=org,
        is_primary=True,
    )

    # 6. Make the user the OWNER of the new org.
    OrganizationMember.objects.create(
        organization=org,
        user=user,
        role=OrganizationMember.Role.OWNER,
    )

    return user


# ---------------------------------------------------------------------------
# Email helpers (Gmail SMTP via Django's send_mail)
# ---------------------------------------------------------------------------

def _send_email(to_email: str, subject: str, html: str, text: str) -> None:
    """Send a transactional email through Django's configured SMTP backend."""
    try:
        send_mail(
            subject=subject,
            message=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("EMAIL [%s] sent to=%s", subject, to_email)
    except Exception as exc:
        logger.error("EMAIL send failed to=%s error=%s", to_email, exc)


def send_verification_email(user, token: str) -> None:
    """Send an email-verification link."""
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    verify_url = f"{frontend_url}/verify-email?token={token}"

    html = (
        f"<p>Hi {user.name or user.email},</p>"
        f"<p>Please verify your email address by clicking the link below:</p>"
        f'<p><a href="{verify_url}">{verify_url}</a></p>'
        f"<p>This link expires in 24 hours.</p>"
    )
    text = (
        f"Hi {user.name or user.email},\n\n"
        f"Please verify your email address by visiting:\n{verify_url}\n\n"
        f"This link expires in 24 hours."
    )
    _send_email(user.email, "Verify your email address", html, text)


def send_password_reset_email(user, token: str) -> None:
    """Send a password-reset link."""
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    reset_url = f"{frontend_url}/reset-password?token={token}"

    html = (
        f"<p>Hi {user.name or user.email},</p>"
        f"<p>We received a request to reset your password. Click the link below:</p>"
        f'<p><a href="{reset_url}">{reset_url}</a></p>'
        f"<p>This link expires in 1 hour. If you did not request this, ignore this email.</p>"
    )
    text = (
        f"Hi {user.name or user.email},\n\n"
        f"We received a request to reset your password. Visit:\n{reset_url}\n\n"
        f"This link expires in 1 hour. If you did not request this, ignore this email."
    )
    _send_email(user.email, "Reset your password", html, text)


def send_invitation_email(to_email: str, org, token: str) -> None:
    """Send an organisation invitation."""
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    invite_url = f"{frontend_url}/accept-invite?token={token}"

    html = (
        f"<p>You have been invited to join <strong>{org.name}</strong> on SocialOS.</p>"
        f'<p><a href="{invite_url}">Accept Invitation</a></p>'
        f"<p>This invitation expires in 7 days.</p>"
    )
    text = (
        f"You have been invited to join {org.name} on SocialOS.\n\n"
        f"Accept your invitation here:\n{invite_url}\n\n"
        f"This invitation expires in 7 days."
    )
    _send_email(to_email, f"You're invited to {org.name}", html, text)


def send_org_deleted_email(user, org_name: str) -> bool:
    """Notify member that their organization was deleted."""
    html = (
        f"<p>Hi {user.name or user.email},</p>"
        f"<p>The organization <strong>{org_name}</strong> has been deleted by its owner.</p>"
        f"<p>You are no longer a member of this organization.</p>"
    )
    text = (
        f"Hi {user.name or user.email},\n\n"
        f"The organization {org_name} has been deleted by its owner.\n"
        f"You are no longer a member of this organization."
    )
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        send_mail(
            subject=f"Organization {org_name} deleted",
            message=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html,
            fail_silently=False,
        )
        return True
    except Exception:
        return False


def send_member_left_email(owner_email: str, member_name: str, org_name: str) -> bool:
    """Notify owner that a member has left the organization."""
    html = (
        f"<p>Hi,</p>"
        f"<p>The member <strong>{member_name}</strong> has left your organization <strong>{org_name}</strong>.</p>"
    )
    text = (
        f"Hi,\n\n"
        f"The member {member_name} has left your organization {org_name}."
    )
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        send_mail(
            subject=f"Member left {org_name}",
            message=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[owner_email],
            html_message=html,
            fail_silently=False,
        )
        return True
    except Exception:
        return False
