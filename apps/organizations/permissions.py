from rest_framework.permissions import BasePermission

from .models import OrganizationMember


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


class IsOrgMember(BasePermission):

    def has_object_permission(self, request, view, obj):
        return _get_org_membership(request.user, obj) is not None


class IsOrgOwnerOrAdmin(BasePermission):

    def has_object_permission(self, request, view, obj):
        membership = _get_org_membership(request.user, obj)
        return membership is not None and membership.role in (
            OrganizationMember.Role.OWNER,
            OrganizationMember.Role.ADMIN,
        )


class IsOrgOwner(BasePermission):

    def has_object_permission(self, request, view, obj):
        membership = _get_org_membership(request.user, obj)
        return (
            membership is not None
            and membership.role == OrganizationMember.Role.OWNER
        )
