"""
Organizations — Services
========================
Business-logic functions that operate on Organisation-related models,
keeping views thin and logic testable.
"""
import logging

from .models import OrganizationInvitation

logger = logging.getLogger(__name__)


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
