"""
Organizations — DRF Permission Classes
=======================================
Object-level permissions scoped to an Organisation instance.

Usage in views::

    class MyView(APIView):
        permission_classes = [IsAuthenticated, IsOrgOwnerOrAdmin]

        def get_object(self):
            org = get_org_or_404(...)
            self.check_object_permissions(self.request, org)
            return org
"""
from rest_framework.permissions import BasePermission

from .models import OrganizationMember


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _get_org_membership(user, org):
    """
    Return the active OrganizationMember for *user* in *org*, or None.
    """
    try:
        return OrganizationMember.objects.get(
            organization=org,
            user=user,
            is_active=True,
        )
    except OrganizationMember.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Permission classes
# ---------------------------------------------------------------------------

class IsOrgMember(BasePermission):
    """
    Object-level permission: user has any active membership in the organisation.

    *obj* must be an :class:`~apps.organizations.models.Organization` instance.
    """

    def has_object_permission(self, request, view, obj):
        return _get_org_membership(request.user, obj) is not None


class IsOrgOwnerOrAdmin(BasePermission):
    """
    Object-level permission: user is OWNER or ADMIN of the organisation.

    *obj* must be an :class:`~apps.organizations.models.Organization` instance.
    """

    def has_object_permission(self, request, view, obj):
        membership = _get_org_membership(request.user, obj)
        return membership is not None and membership.role in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        )


class IsOrgOwner(BasePermission):
    """
    Object-level permission: user is the OWNER of the organisation.

    *obj* must be an :class:`~apps.organizations.models.Organization` instance.
    """

    def has_object_permission(self, request, view, obj):
        membership = _get_org_membership(request.user, obj)
        return (
            membership is not None
            and membership.role == OrganizationMember.Role.OWNER
        )
