"""
Auth Core — RBAC Permission Classes
=====================================
Role hierarchy (highest → lowest):
  owner > admin > editor > viewer

Usage in ViewSets:
  permission_classes = [IsAuthenticated, IsEditor]
  permission_classes = [IsAuthenticated, IsAdmin]
  permission_classes = [IsAuthenticated, IsOwner]
"""
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class HasOrgRole(BasePermission):
    """
    Base permission that checks whether the authenticated user holds at least
    `required_role` in their active organization.

    Subclass and override `required_role` — do NOT use this class directly.
    """

    required_role: str = "viewer"

    # Ordered from highest to lowest privilege.
    ROLE_HIERARCHY = ["owner", "admin", "editor", "viewer"]

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        # request.membership is attached by TenantIsolationMiddleware / JWT auth.
        membership = getattr(request, "membership", None)
        if not membership:
            return False

        return membership.role in self._get_allowed_roles()

    def _get_allowed_roles(self) -> list[str]:
        """Return all roles that satisfy the required_role level (inclusive)."""
        try:
            idx = self.ROLE_HIERARCHY.index(self.required_role)
        except ValueError:
            return []
        return self.ROLE_HIERARCHY[: idx + 1]


class IsViewer(HasOrgRole):
    """Allows any authenticated org member (viewer and above)."""
    required_role = "viewer"


class IsEditor(HasOrgRole):
    """Allows editors, admins, and owners."""
    required_role = "editor"


class IsAdmin(HasOrgRole):
    """Allows admins and owners only."""
    required_role = "admin"


class IsOwner(HasOrgRole):
    """Allows the organization owner only."""
    required_role = "owner"
