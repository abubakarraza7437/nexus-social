"""
Tests for multi-tenant / organization isolation.

Covers two properties:
  1. Cross-org access is blocked  — User A cannot read/write User B's org data
  2. Query filtering              — DB queries are scoped to the requesting user's orgs

Schema-level isolation is enforced by django-tenants (TenantMainMiddleware +
per-tenant PostgreSQL schema). The old RLS-based TenantIsolationMiddleware has
been removed; these tests verify application-layer access control only.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationMember
from tests.factories import OrganizationFactory, OrganizationMemberFactory, UserFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_a(db) -> User:
    return User.objects.create_user(
        email="user_a@example.com",
        password="TestPass123!",
        name="User A",
        is_active=True,
    )


@pytest.fixture
def user_b(db) -> User:
    return User.objects.create_user(
        email="user_b@example.com",
        password="TestPass123!",
        name="User B",
        is_active=True,
    )


@pytest.fixture
def org_a(db) -> Organization:
    return OrganizationFactory(name="Org A", slug="org-a")


@pytest.fixture
def org_b(db) -> Organization:
    return OrganizationFactory(name="Org B", slug="org-b")


@pytest.fixture
def membership_a(user_a: User, org_a: Organization) -> OrganizationMember:
    """User A is OWNER of Org A."""
    return OrganizationMemberFactory(
        user=user_a, organization=org_a, role=OrganizationMember.Role.OWNER
    )


@pytest.fixture
def membership_b(user_b: User, org_b: Organization) -> OrganizationMember:
    """User B is OWNER of Org B."""
    return OrganizationMemberFactory(
        user=user_b, organization=org_b, role=OrganizationMember.Role.OWNER
    )


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# 1. Cross-org access — User A cannot access User B's org data
# ---------------------------------------------------------------------------


class TestCrossOrgAccess:
    """User A must not be able to read or modify Org B's data."""

    def test_user_a_cannot_view_org_b_detail(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            org_b: Organization,
    ) -> None:
        """GET /api/v1/orgs/{org_b.id}/ returns 403 for User A."""
        response = _client_for(user_a).get(f"/api/v1/orgs/{org_b.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_a_cannot_list_org_b_members(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            org_b: Organization,
    ) -> None:
        """GET /api/v1/orgs/{org_b.id}/members/ returns 403 for User A."""
        response = _client_for(user_a).get(f"/api/v1/orgs/{org_b.id}/members/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_a_cannot_invite_to_org_b(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            org_b: Organization,
    ) -> None:
        """POST /api/v1/orgs/{org_b.id}/invite/ returns 403 for User A."""
        payload = {"email": "outsider@example.com", "role": "viewer"}
        response = _client_for(user_a).post(
            f"/api/v1/orgs/{org_b.id}/invite/", payload, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_a_cannot_update_org_b_member(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            org_b: Organization,
    ) -> None:
        """PATCH /api/v1/orgs/{org_b.id}/members/{mid}/ returns 403 for User A."""
        url = f"/api/v1/orgs/{org_b.id}/members/{membership_b.id}/"
        response = _client_for(user_a).patch(url, {"role": "admin"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_a_cannot_remove_org_b_member(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            org_b: Organization,
    ) -> None:
        """DELETE /api/v1/orgs/{org_b.id}/members/{mid}/ returns 403 for User A."""
        url = f"/api/v1/orgs/{org_b.id}/members/{membership_b.id}/"
        response = _client_for(user_a).delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_user_cannot_view_any_org(
            self,
            org_a: Organization,
    ) -> None:
        """Unauthenticated requests are rejected before org isolation is even checked."""
        response = APIClient().get(f"/api/v1/orgs/{org_a.id}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# 2. Query filtering — org list and member list are scoped to the requesting user
# ---------------------------------------------------------------------------


class TestQueryFiltering:
    """Queryset results must only contain records belonging to the requesting user."""

    def test_org_list_returns_only_own_orgs(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            org_a: Organization,
            org_b: Organization,
    ) -> None:
        """User A's org list contains Org A only, not Org B."""
        response = _client_for(user_a).get("/api/v1/orgs/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data.get("results") or data.get("data") or data
        org_ids = {str(r["id"]) for r in results}
        assert str(org_a.id) in org_ids
        assert str(org_b.id) not in org_ids

    def test_org_list_excludes_orgs_with_inactive_membership(
            self,
            user_a: User,
            org_a: Organization,
            org_b: Organization,
    ) -> None:
        """Inactive memberships do not appear in the org list."""
        OrganizationMemberFactory(user=user_a, organization=org_a, is_active=True)
        OrganizationMemberFactory(user=user_a, organization=org_b, is_active=False)

        response = _client_for(user_a).get("/api/v1/orgs/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data.get("results") or data.get("data") or data
        org_ids = {str(r["id"]) for r in results}
        assert str(org_a.id) in org_ids
        assert str(org_b.id) not in org_ids

    def test_member_list_returns_only_members_of_requested_org(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            org_a: Organization,
    ) -> None:
        """Member list for Org A contains only Org A members, not Org B members."""
        extra_member = OrganizationMemberFactory(
            organization=org_a, role=OrganizationMember.Role.VIEWER
        )

        response = _client_for(user_a).get(f"/api/v1/orgs/{org_a.id}/members/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data.get("results") or data.get("data") or data
        member_ids = {str(r["id"]) for r in results}

        assert str(membership_a.id) in member_ids
        assert str(extra_member.id) in member_ids
        assert str(membership_b.id) not in member_ids

    def test_member_list_excludes_inactive_members(
            self,
            user_a: User,
            org_a: Organization,
    ) -> None:
        """Inactive members are filtered out of the member list."""
        active = OrganizationMemberFactory(
            user=user_a, organization=org_a, role=OrganizationMember.Role.OWNER
        )
        inactive_user = UserFactory()
        inactive = OrganizationMemberFactory(
            user=inactive_user, organization=org_a, is_active=False
        )

        response = _client_for(user_a).get(f"/api/v1/orgs/{org_a.id}/members/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data.get("results") or data.get("data") or data
        member_ids = {str(r["id"]) for r in results}
        assert str(active.id) in member_ids
        assert str(inactive.id) not in member_ids

    def test_two_users_see_independent_org_lists(
            self,
            membership_a: OrganizationMember,
            membership_b: OrganizationMember,
            user_a: User,
            user_b: User,
            org_a: Organization,
            org_b: Organization,
    ) -> None:
        """User A and User B each see only their own org — no bleed between users."""
        resp_a = _client_for(user_a).get("/api/v1/orgs/")
        resp_b = _client_for(user_b).get("/api/v1/orgs/")

        assert resp_a.status_code == status.HTTP_200_OK
        assert resp_b.status_code == status.HTTP_200_OK

        def _ids(resp):
            data = resp.data
            results = data.get("results") or data.get("data") or data
            return {str(r["id"]) for r in results}

        ids_a = _ids(resp_a)
        ids_b = _ids(resp_b)

        assert str(org_a.id) in ids_a
        assert str(org_b.id) not in ids_a

        assert str(org_b.id) in ids_b
        assert str(org_a.id) not in ids_b
