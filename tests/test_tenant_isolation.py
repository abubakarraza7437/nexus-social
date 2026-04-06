"""
Tests for multi-tenant / organization isolation.

Covers three properties:
  1. Cross-org access is blocked  — User A cannot read/write User B's org data
  2. Query filtering              — DB queries are scoped to the requesting user's orgs
  3. Middleware tenant attachment — TenantIsolationMiddleware sets app.current_org_id
"""
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.organizations.middleware import TenantIsolationMiddleware
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
        payload = {"email": "outsider@example.com", "role": "member"}
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
        # Add a second member to Org A so we can verify the count precisely
        extra_member = OrganizationMemberFactory(
            organization=org_a, role=OrganizationMember.Role.MEMBER
        )

        response = _client_for(user_a).get(f"/api/v1/orgs/{org_a.id}/members/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data.get("results") or data.get("data") or data
        member_ids = {str(r["id"]) for r in results}

        # Org A has user_a (owner) + extra_member
        assert str(membership_a.id) in member_ids
        assert str(extra_member.id) in member_ids
        # Org B's owner membership must NOT appear
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


# ---------------------------------------------------------------------------
# 3. Middleware — TenantIsolationMiddleware attaches tenant to the connection
# ---------------------------------------------------------------------------


class TestTenantIsolationMiddleware:
    """TenantIsolationMiddleware must set app.current_org_id when request.org is present."""

    def _make_middleware(self):
        get_response = MagicMock(return_value=MagicMock())
        return TenantIsolationMiddleware(get_response)

    def _make_request(self, org=None):
        request = MagicMock()
        if org is not None:
            request.org = org
        else:
            # simulate no `org` attribute (unauthenticated / no membership)
            del request.org
        return request

    def test_sets_current_org_id_when_org_present(self, org_a: Organization) -> None:
        """process_view executes SET LOCAL with the org's UUID."""
        middleware = self._make_middleware()
        request = self._make_request(org=org_a)

        with patch("apps.organizations.middleware.connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = middleware.process_view(request, MagicMock(), [], {})

        assert result is None  # must not short-circuit the view
        mock_cursor.execute.assert_called_once_with(
            "SET LOCAL app.current_org_id = %s",
            [str(org_a.id)],
        )

    def test_noop_when_no_org_on_request(self) -> None:
        """process_view is a no-op for unauthenticated / org-less requests."""
        middleware = self._make_middleware()
        request = self._make_request(org=None)

        with patch("apps.organizations.middleware.connection") as mock_conn:
            result = middleware.process_view(request, MagicMock(), [], {})

        assert result is None
        mock_conn.cursor.assert_not_called()

    def test_does_not_short_circuit_when_org_present(self, org_a: Organization) -> None:
        """process_view must return None (let Django continue to the view)."""
        middleware = self._make_middleware()
        request = self._make_request(org=org_a)

        with patch("apps.organizations.middleware.connection"):
            result = middleware.process_view(request, MagicMock(), [], {})

        assert result is None

    def test_gracefully_handles_db_error(self, org_a: Organization) -> None:
        """A cursor error must be swallowed so the request is not broken."""
        middleware = self._make_middleware()
        request = self._make_request(org=org_a)

        with patch("apps.organizations.middleware.connection") as mock_conn:
            mock_conn.cursor.side_effect = Exception("DB unavailable")

            # Should not raise
            result = middleware.process_view(request, MagicMock(), [], {})

        assert result is None

    def test_different_orgs_produce_different_ids(
            self, org_a: Organization, org_b: Organization
    ) -> None:
        """Each org gets its own UUID written to the session variable."""
        middleware = self._make_middleware()
        executed = []

        def capture_execute(sql, params):
            executed.append(params[0])

        for org in (org_a, org_b):
            request = self._make_request(org=org)
            with patch("apps.organizations.middleware.connection") as mock_conn:
                mock_cursor = MagicMock()
                mock_cursor.execute.side_effect = capture_execute
                mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
                mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
                middleware.process_view(request, MagicMock(), [], {})

        assert executed[0] == str(org_a.id)
        assert executed[1] == str(org_b.id)
        assert executed[0] != executed[1]
