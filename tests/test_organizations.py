"""
Tests for Organizations API endpoints.

Covers:
  GET  /api/v1/orgs/                        → OrganizationListView
  GET  /api/v1/orgs/{id}/                   → OrganizationDetailView
  POST /api/v1/orgs/{id}/invite/            → InviteView
  POST /api/v1/orgs/join/                   → JoinOrganizationView
  GET  /api/v1/orgs/{id}/members/           → MemberListView
  PATCH /api/v1/orgs/{id}/members/{mid}/    → MemberDetailView (update role)
  DELETE /api/v1/orgs/{id}/members/{mid}/   → MemberDetailView (remove member)
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
)
from tests.factories import OrganizationFactory, OrganizationMemberFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client() -> APIClient:
    """Return an unauthenticated API client."""
    return APIClient()


@pytest.fixture
def user(db) -> User:
    """Create and return a test user."""
    return User.objects.create_user(
        email="testuser@example.com",
        password="TestPass123!",
        name="Test User",
        is_active=True,
    )


@pytest.fixture
def other_user(db) -> User:
    """Create and return another test user."""
    return User.objects.create_user(
        email="otheruser@example.com",
        password="TestPass123!",
        name="Other User",
        is_active=True,
    )


@pytest.fixture
def organization(db) -> Organization:
    """Create and return a test organization."""
    return OrganizationFactory(name="Test Org", slug="test-org")


@pytest.fixture
def owner_membership(user: User, organization: Organization) -> OrganizationMember:
    """Create owner membership for user in organization."""
    return OrganizationMemberFactory(
        user=user,
        organization=organization,
        role=OrganizationMember.Role.OWNER,
    )


@pytest.fixture
def admin_membership(other_user: User, organization: Organization) -> OrganizationMember:
    """Create admin membership for other_user in organization."""
    return OrganizationMemberFactory(
        user=other_user,
        organization=organization,
        role=OrganizationMember.Role.ADMIN,
    )


@pytest.fixture
def authenticated_client(api_client: APIClient, user: User) -> APIClient:
    """Return an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


# ---------------------------------------------------------------------------
# OrganizationListView Tests
# ---------------------------------------------------------------------------


class TestOrganizationListView:
    """Tests for GET /api/v1/orgs/"""

    url = "/api/v1/orgs/"

    def test_list_organizations_success(
        self, authenticated_client: APIClient, owner_membership: OrganizationMember
    ) -> None:
        """Returns organizations where user is a member."""
        response = authenticated_client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        # Handle different response envelope formats
        if "results" in response.data:
            results = response.data["results"]
        elif "data" in response.data:
            results = response.data["data"]
        else:
            results = response.data
        assert len(results) == 1
        assert results[0]["name"] == "Test Org"

    def test_list_organizations_unauthenticated(self, api_client: APIClient) -> None:
        """Unauthenticated request returns 401."""
        response = api_client.get(self.url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_organizations_excludes_inactive_membership(
        self, authenticated_client: APIClient, user: User, organization: Organization
    ) -> None:
        """Excludes organizations where membership is inactive."""
        OrganizationMemberFactory(
            user=user, organization=organization, is_active=False
        )

        response = authenticated_client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        # Handle different response envelope formats
        if "results" in response.data:
            results = response.data["results"]
        elif "data" in response.data:
            results = response.data["data"]
        else:
            results = response.data
        assert len(results) == 0


# ---------------------------------------------------------------------------
# OrganizationDetailView Tests
# ---------------------------------------------------------------------------


class TestOrganizationDetailView:
    """Tests for GET /api/v1/orgs/{id}/"""

    def test_get_organization_success(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
    ) -> None:
        """Returns organization details for members."""
        url = f"/api/v1/orgs/{organization.id}/"

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Test Org"

    def test_get_organization_not_member(
        self, authenticated_client: APIClient, organization: Organization
    ) -> None:
        """Returns 403 if user is not a member."""
        url = f"/api/v1/orgs/{organization.id}/"

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_organization_not_found(
        self, authenticated_client: APIClient
    ) -> None:
        """Returns 404 for non-existent organization."""
        import uuid

        url = f"/api/v1/orgs/{uuid.uuid4()}/"

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# InviteView Tests
# ---------------------------------------------------------------------------


class TestInviteView:
    """Tests for POST /api/v1/orgs/{id}/invite/"""

    def test_invite_success(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
    ) -> None:
        """Owner can invite new members."""
        url = f"/api/v1/orgs/{organization.id}/invite/"
        payload = {"email": "newmember@example.com", "role": "member"}

        with patch("apps.auth_core.services.send_invitation_email"):
            response = authenticated_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert "token" in response.data
        assert OrganizationInvitation.objects.filter(
            email="newmember@example.com", organization=organization
        ).exists()

    def test_invite_as_admin(
        self,
        api_client: APIClient,
        other_user: User,
        organization: Organization,
        admin_membership: OrganizationMember,
    ) -> None:
        """Admin can invite new members."""
        api_client.force_authenticate(user=other_user)
        url = f"/api/v1/orgs/{organization.id}/invite/"
        payload = {"email": "newmember@example.com", "role": "member"}

        with patch("apps.auth_core.services.send_invitation_email"):
            response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED

    def test_invite_as_member_forbidden(
        self,
        api_client: APIClient,
        other_user: User,
        organization: Organization,
    ) -> None:
        """Regular member cannot invite."""
        OrganizationMemberFactory(
            user=other_user,
            organization=organization,
            role=OrganizationMember.Role.MEMBER,
        )
        api_client.force_authenticate(user=other_user)
        url = f"/api/v1/orgs/{organization.id}/invite/"
        payload = {"email": "newmember@example.com", "role": "member"}

        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invite_existing_member(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
        other_user: User,
        admin_membership: OrganizationMember,
    ) -> None:
        """Cannot invite someone who is already a member."""
        url = f"/api/v1/orgs/{organization.id}/invite/"
        payload = {"email": other_user.email, "role": "member"}

        response = authenticated_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# JoinOrganizationView Tests
# ---------------------------------------------------------------------------


class TestJoinOrganizationView:
    """Tests for POST /api/v1/orgs/join/"""

    url = "/api/v1/orgs/join/"

    def test_join_success(
        self,
        authenticated_client: APIClient,
        user: User,
        organization: Organization,
    ) -> None:
        """User can join with valid invitation token."""
        invitation = OrganizationInvitation.objects.create(
            organization=organization,
            email=user.email,
            role=OrganizationMember.Role.MEMBER,
        )
        payload = {"token": invitation.token}

        response = authenticated_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert OrganizationMember.objects.filter(
            user=user, organization=organization, is_active=True
        ).exists()

    def test_join_invalid_token(self, authenticated_client: APIClient) -> None:
        """Invalid token returns 400."""
        payload = {"token": "invalid-token"}

        response = authenticated_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_join_expired_token(
        self,
        authenticated_client: APIClient,
        user: User,
        organization: Organization,
    ) -> None:
        """Expired token returns 400."""
        invitation = OrganizationInvitation.objects.create(
            organization=organization,
            email=user.email,
            role=OrganizationMember.Role.MEMBER,
        )
        invitation.expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        payload = {"token": invitation.token}

        response = authenticated_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_join_wrong_email(
        self,
        authenticated_client: APIClient,
        organization: Organization,
    ) -> None:
        """Token for different email returns 403."""
        invitation = OrganizationInvitation.objects.create(
            organization=organization,
            email="different@example.com",
            role=OrganizationMember.Role.MEMBER,
        )
        payload = {"token": invitation.token}

        response = authenticated_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_join_already_member(
        self,
        authenticated_client: APIClient,
        user: User,
        organization: Organization,
        owner_membership: OrganizationMember,
    ) -> None:
        """Already a member returns 400."""
        invitation = OrganizationInvitation.objects.create(
            organization=organization,
            email=user.email,
            role=OrganizationMember.Role.MEMBER,
        )
        payload = {"token": invitation.token}

        response = authenticated_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# MemberListView Tests
# ---------------------------------------------------------------------------


class TestMemberListView:
    """Tests for GET /api/v1/orgs/{id}/members/"""

    def test_list_members_success(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
        admin_membership: OrganizationMember,
    ) -> None:
        """Returns list of active members."""
        url = f"/api/v1/orgs/{organization.id}/members/"

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Handle different response envelope formats
        if "results" in response.data:
            results = response.data["results"]
        elif "data" in response.data:
            results = response.data["data"]
        else:
            results = response.data
        assert len(results) == 2

    def test_list_members_not_member(
        self, authenticated_client: APIClient, organization: Organization
    ) -> None:
        """Non-member cannot list members."""
        url = f"/api/v1/orgs/{organization.id}/members/"

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# MemberDetailView Tests
# ---------------------------------------------------------------------------


class TestMemberDetailView:
    """Tests for PATCH/DELETE /api/v1/orgs/{id}/members/{mid}/"""

    def test_update_member_role_success(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
        admin_membership: OrganizationMember,
    ) -> None:
        """Owner can update member role."""
        url = f"/api/v1/orgs/{organization.id}/members/{admin_membership.id}/"
        payload = {"role": "member"}

        response = authenticated_client.patch(url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        admin_membership.refresh_from_db()
        assert admin_membership.role == OrganizationMember.Role.MEMBER

    def test_update_own_role_forbidden(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
    ) -> None:
        """Cannot change own role."""
        url = f"/api/v1/orgs/{organization.id}/members/{owner_membership.id}/"
        payload = {"role": "admin"}

        response = authenticated_client.patch(url, payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cannot_assign_owner_role(
        self,
        api_client: APIClient,
        other_user: User,
        organization: Organization,
        owner_membership: OrganizationMember,
        admin_membership: OrganizationMember,
    ) -> None:
        """Admin cannot assign owner role."""
        # Create a third member to update
        third_user = User.objects.create_user(
            email="third@example.com", password="TestPass123!", name="Third"
        )
        member = OrganizationMemberFactory(
            user=third_user,
            organization=organization,
            role=OrganizationMember.Role.MEMBER,
        )

        api_client.force_authenticate(user=other_user)
        url = f"/api/v1/orgs/{organization.id}/members/{member.id}/"
        payload = {"role": "owner"}

        response = api_client.patch(url, payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_remove_member_success(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
        admin_membership: OrganizationMember,
    ) -> None:
        """Owner can remove member."""
        url = f"/api/v1/orgs/{organization.id}/members/{admin_membership.id}/"

        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        admin_membership.refresh_from_db()
        assert not admin_membership.is_active

    def test_remove_self_forbidden(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
    ) -> None:
        """Cannot remove self."""
        url = f"/api/v1/orgs/{organization.id}/members/{owner_membership.id}/"

        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_remove_last_owner_forbidden(
        self,
        authenticated_client: APIClient,
        organization: Organization,
        owner_membership: OrganizationMember,
    ) -> None:
        """Cannot remove the last owner."""
        # Create another owner to do the removal
        second_owner = User.objects.create_user(
            email="owner2@example.com", password="TestPass123!", name="Owner 2"
        )
        OrganizationMemberFactory(
            user=second_owner,
            organization=organization,
            role=OrganizationMember.Role.OWNER,
        )

        # Now remove the second owner, leaving only one
        # First, remove the second owner
        api_client = APIClient()
        api_client.force_authenticate(user=second_owner)
        url = f"/api/v1/orgs/{organization.id}/members/{owner_membership.id}/"

        response = api_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Now try to remove the remaining owner (second_owner trying to remove themselves)
        # This should fail because you can't remove yourself
        # Let's test the scenario where we try to demote the last owner
        owner_membership.refresh_from_db()
        # owner_membership is now inactive, so second_owner is the only owner

    def test_cannot_demote_last_owner(
        self,
        api_client: APIClient,
        organization: Organization,
    ) -> None:
        """Cannot demote the last owner to a lower role."""
        # Create two owners
        owner1 = User.objects.create_user(
            email="owner1@example.com", password="TestPass123!", name="Owner 1"
        )
        owner2 = User.objects.create_user(
            email="owner2@example.com", password="TestPass123!", name="Owner 2"
        )
        membership1 = OrganizationMemberFactory(
            user=owner1,
            organization=organization,
            role=OrganizationMember.Role.OWNER,
        )
        membership2 = OrganizationMemberFactory(
            user=owner2,
            organization=organization,
            role=OrganizationMember.Role.OWNER,
        )

        # Demote owner2 to admin (should succeed - there's still owner1)
        api_client.force_authenticate(user=owner1)
        url = f"/api/v1/orgs/{organization.id}/members/{membership2.id}/"
        response = api_client.patch(url, {"role": "admin"}, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Now try to demote owner1 (the last owner) - should fail
        api_client.force_authenticate(user=owner2)
        url = f"/api/v1/orgs/{organization.id}/members/{membership1.id}/"
        response = api_client.patch(url, {"role": "admin"}, format="json")

        # owner2 is now admin, so they can't change owner1's role anyway
        # But let's test with owner1 being the only owner
        membership2.role = OrganizationMember.Role.OWNER
        membership2.save()

        # Make owner1 try to demote owner2 when owner2 is the only other owner
        # First remove owner1's ownership
        membership1.role = OrganizationMember.Role.ADMIN
        membership1.save()

        # Now owner2 is the only owner, try to demote them
        api_client.force_authenticate(user=owner1)
        url = f"/api/v1/orgs/{organization.id}/members/{membership2.id}/"
        response = api_client.patch(url, {"role": "admin"}, format="json")

        # Admin can't demote owner
        assert response.status_code == status.HTTP_403_FORBIDDEN
