"""
Auth Core — Services
====================
Business-logic functions for user registration, organisation bootstrapping,
and transactional email dispatch (mocked via logging until a real provider
is wired in).
"""
import logging
import re
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
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
def create_user_with_organization(validated_data: dict) -> User:
    """
    Atomically create a User, generate an email-verification token, bootstrap
    a personal Organisation (with its PostgreSQL schema and primary Domain),
    and assign the user as OWNER.

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

    # 2. Email verification token + mock send.
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
# Mock email helpers (replace with Celery tasks / email provider later)
# ---------------------------------------------------------------------------

def send_verification_email(user, token: str) -> None:
    """Log a mock verification email."""
    logger.info(
        "MOCK EMAIL [verification] to=%s token=%s",
        user.email,
        token,
    )


def send_password_reset_email(user, token: str) -> None:
    """Log a mock password-reset email."""
    logger.info(
        "MOCK EMAIL [password_reset] to=%s token=%s",
        user.email,
        token,
    )


def send_invitation_email(to_email: str, org, token: str) -> None:
    """Log a mock org-invitation email."""
    logger.info(
        "MOCK EMAIL [invitation] to=%s org=%s token=%s",
        to_email,
        org.name,
        token,
    )
