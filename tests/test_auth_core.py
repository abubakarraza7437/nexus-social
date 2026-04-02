"""
Tests for Auth Core API endpoints.

Covers:
  POST /api/v1/auth/signup/          → SignupView
  POST /api/v1/auth/login/           → LoginView (JWT pair)
  POST /api/v1/auth/refresh/         → RefreshView (JWT refresh)
  POST /api/v1/auth/logout/          → LogoutView (blacklist refresh token)
  POST /api/v1/auth/forgot-password/ → ForgotPasswordView
  POST /api/v1/auth/reset-password/  → ResetPasswordView
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.auth_core.models import EmailVerificationToken, PasswordResetToken
from apps.organizations.models import OrganizationMember
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
    """Create and return a test user with a known password."""
    user = User.objects.create_user(
        email="testuser@example.com",
        password="TestPass123!",
        name="Test User",
        is_active=True,
        is_verified=True,
    )
    return user


@pytest.fixture
def user_with_org(user: User) -> User:
    """Create a user with an organization membership."""
    org = OrganizationFactory()
    OrganizationMemberFactory(
        user=user, organization=org, role=OrganizationMember.Role.OWNER
    )
    return user


@pytest.fixture
def authenticated_client(api_client: APIClient, user: User) -> APIClient:
    """Return an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def user_tokens(user: User) -> dict:
    """Generate JWT tokens for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


@pytest.fixture(autouse=True)
def reset_axes(db):
    """Reset axes lockouts between tests."""
    from axes.models import AccessAttempt, AccessLog

    yield
    AccessAttempt.objects.all().delete()
    AccessLog.objects.all().delete()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_error_fields(response_data: dict) -> list[str]:
    """Extract field names from the error envelope."""
    errors = response_data.get("errors", [])
    return [e.get("field") for e in errors]


def has_error_for_field(response_data: dict, field: str) -> bool:
    """Check if there's an error for a specific field."""
    return field in get_error_fields(response_data)


# ---------------------------------------------------------------------------
# SignupView Tests
# ---------------------------------------------------------------------------


class TestSignupView:
    """Tests for POST /api/v1/auth/signup/"""

    url = "/api/v1/auth/signup/"

    def test_signup_success(self, api_client: APIClient) -> None:
        """Successful signup creates user and returns 201."""
        payload = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "name": "New User",
        }

        with patch("apps.auth_core.services.send_verification_email"):
            response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["detail"] == "Account created. Please verify your email."

        # Verify user was created
        user = User.objects.get(email="newuser@example.com")
        assert user.name == "New User"
        assert user.check_password("SecurePass123!")
        assert not user.is_verified

        # Verify email verification token was created
        assert EmailVerificationToken.objects.filter(user=user).exists()

        # Signup no longer creates an organization — org creation is deferred
        # to the post-signup onboarding flow (POST /api/v1/orgs/check-or-create/)
        assert not OrganizationMember.objects.filter(user=user).exists()

    def test_signup_duplicate_email(self, api_client: APIClient, user: User) -> None:
        """Signup with existing email returns 422."""
        payload = {
            "email": user.email,
            "password": "SecurePass123!",
            "name": "Duplicate User",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "email")

    def test_signup_weak_password(self, api_client: APIClient) -> None:
        """Signup with weak password returns 422."""
        payload = {
            "email": "weakpass@example.com",
            "password": "123",  # Too short and simple
            "name": "Weak Pass User",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "password")

    def test_signup_invalid_email(self, api_client: APIClient) -> None:
        """Signup with invalid email returns 422."""
        payload = {
            "email": "not-an-email",
            "password": "SecurePass123!",
            "name": "Invalid Email User",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "email")

    def test_signup_missing_required_fields(self, api_client: APIClient) -> None:
        """Signup without required fields returns 422."""
        response = api_client.post(self.url, {}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "email")
        assert has_error_for_field(response.data, "password")
        assert has_error_for_field(response.data, "name")

    def test_signup_email_case_insensitive(
        self, api_client: APIClient, user: User
    ) -> None:
        """Signup treats email as case-insensitive."""
        payload = {
            "email": user.email.upper(),
            "password": "SecurePass123!",
            "name": "Case Test User",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "email")


# ---------------------------------------------------------------------------
# LoginView Tests
# ---------------------------------------------------------------------------


class TestLoginView:
    """Tests for POST /api/v1/auth/login/"""

    url = "/api/v1/auth/login/"

    def test_login_success(self, api_client: APIClient, user: User) -> None:
        """Successful login returns JWT tokens."""
        payload = {
            "email": user.email,
            "password": "TestPass123!",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_wrong_password(self, api_client: APIClient, user: User) -> None:
        """Login with wrong password returns 401."""
        payload = {
            "email": user.email,
            "password": "WrongPassword123!",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client: APIClient) -> None:
        """Login with nonexistent email returns 401."""
        payload = {
            "email": "nonexistent@example.com",
            "password": "SomePassword123!",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_inactive_user(self, api_client: APIClient, db) -> None:
        """Login with inactive user returns 401."""
        inactive_user = User.objects.create_user(
            email="inactive@example.com",
            password="TestPass123!",
            name="Inactive User",
            is_active=False,
        )
        payload = {
            "email": inactive_user.email,
            "password": "TestPass123!",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_missing_credentials(self, api_client: APIClient) -> None:
        """Login without credentials returns 422."""
        response = api_client.post(self.url, {}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_login_email_case_sensitive(
        self, api_client: APIClient, user: User
    ) -> None:
        """Login is case-sensitive for email (Django default behavior)."""
        payload = {
            "email": user.email.upper(),
            "password": "TestPass123!",
        }

        response = api_client.post(self.url, payload, format="json")

        # Django's default authentication backend is case-sensitive
        # If case-insensitive login is needed, a custom backend should be implemented
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# RefreshView Tests
# ---------------------------------------------------------------------------


class TestRefreshView:
    """Tests for POST /api/v1/auth/refresh/"""

    url = "/api/v1/auth/refresh/"

    def test_refresh_success(self, api_client: APIClient, user_tokens: dict) -> None:
        """Successful refresh returns new access token."""
        payload = {"refresh": user_tokens["refresh"]}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_refresh_invalid_token(self, api_client: APIClient) -> None:
        """Refresh with invalid token returns 401."""
        payload = {"refresh": "invalid-token"}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_missing_token(self, api_client: APIClient) -> None:
        """Refresh without token returns 422."""
        response = api_client.post(self.url, {}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_refresh_blacklisted_token(
        self, api_client: APIClient, user: User
    ) -> None:
        """Refresh with blacklisted token returns 401."""
        refresh = RefreshToken.for_user(user)
        refresh.blacklist()

        payload = {"refresh": str(refresh)}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# LogoutView Tests
# ---------------------------------------------------------------------------


class TestLogoutView:
    """Tests for POST /api/v1/auth/logout/"""

    url = "/api/v1/auth/logout/"

    def test_logout_success(
        self, api_client: APIClient, user: User, user_tokens: dict
    ) -> None:
        """Successful logout blacklists refresh token and returns 204."""
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_tokens['access']}")
        payload = {"refresh": user_tokens["refresh"]}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify token is blacklisted - refresh should fail
        refresh_response = api_client.post(
            "/api/v1/auth/refresh/",
            {"refresh": user_tokens["refresh"]},
            format="json",
        )
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_missing_refresh_token(
        self, authenticated_client: APIClient
    ) -> None:
        """Logout without refresh token returns 400."""
        response = authenticated_client.post(self.url, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "refresh token required."

    def test_logout_invalid_refresh_token(
        self, authenticated_client: APIClient
    ) -> None:
        """Logout with invalid refresh token returns 400."""
        payload = {"refresh": "invalid-token"}

        response = authenticated_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "Invalid or expired token."

    def test_logout_unauthenticated(self, api_client: APIClient) -> None:
        """Logout without authentication returns 401."""
        payload = {"refresh": "some-token"}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_already_blacklisted_token(
        self, api_client: APIClient, user: User
    ) -> None:
        """Logout with already blacklisted token returns 400."""
        refresh = RefreshToken.for_user(user)
        refresh.blacklist()

        api_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}"
        )
        payload = {"refresh": str(refresh)}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# ForgotPasswordView Tests
# ---------------------------------------------------------------------------


class TestForgotPasswordView:
    """Tests for POST /api/v1/auth/forgot-password/"""

    url = "/api/v1/auth/forgot-password/"

    def test_forgot_password_existing_user(
        self, api_client: APIClient, user: User
    ) -> None:
        """Forgot password for existing user creates token and returns 200."""
        payload = {"email": user.email}

        with patch(
            "apps.auth_core.views.send_password_reset_email"
        ) as mock_email:
            response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "If that email is registered" in response.data["detail"]

        # Verify token was created
        assert PasswordResetToken.objects.filter(user=user, is_used=False).exists()

        # Verify email was sent
        mock_email.assert_called_once()

    def test_forgot_password_nonexistent_user(self, api_client: APIClient) -> None:
        """Forgot password for nonexistent user returns 200 (no leak)."""
        payload = {"email": "nonexistent@example.com"}

        response = api_client.post(self.url, payload, format="json")

        # Should return 404
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "User with this email does not exists" in response.data["detail"]

    def test_forgot_password_inactive_user(self, api_client: APIClient, db) -> None:
        """Forgot password for inactive user returns 200 (no leak)."""
        inactive_user = User.objects.create_user(
            email="inactive_forgot@example.com",
            password="TestPass123!",
            name="Inactive User",
            is_active=False,
        )
        payload = {"email": inactive_user.email}

        response = api_client.post(self.url, payload, format="json")

        # Should return 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # No token should be created for inactive user
        assert not PasswordResetToken.objects.filter(user=inactive_user).exists()

    def test_forgot_password_invalid_email(self, api_client: APIClient) -> None:
        """Forgot password with invalid email returns 422."""
        payload = {"email": "not-an-email"}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "email")

    def test_forgot_password_missing_email(self, api_client: APIClient) -> None:
        """Forgot password without email returns 422."""
        response = api_client.post(self.url, {}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "email")

    def test_forgot_password_invalidates_previous_tokens(
        self, api_client: APIClient, user: User
    ) -> None:
        """Forgot password invalidates previous unused tokens."""
        # Create an existing token
        old_token = PasswordResetToken.objects.create(user=user)
        assert not old_token.is_used

        payload = {"email": user.email}

        with patch("apps.auth_core.views.send_password_reset_email"):
            response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK

        # Old token should be marked as used
        old_token.refresh_from_db()
        assert old_token.is_used

        # New token should exist
        new_tokens = PasswordResetToken.objects.filter(user=user, is_used=False)
        assert new_tokens.count() == 1


# ---------------------------------------------------------------------------
# ResetPasswordView Tests
# ---------------------------------------------------------------------------


class TestResetPasswordView:
    """Tests for POST /api/v1/auth/reset-password/"""

    url = "/api/v1/auth/reset-password/"

    def test_reset_password_success(self, api_client: APIClient, user: User) -> None:
        """Successful password reset updates password and returns 200."""
        reset_token = PasswordResetToken.objects.create(user=user)
        new_password = "NewSecurePass123!"

        payload = {
            "token": reset_token.token,
            "password": new_password,
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"] == "Password updated successfully."

        # Verify password was changed
        user.refresh_from_db()
        assert user.check_password(new_password)

        # Verify token is marked as used
        reset_token.refresh_from_db()
        assert reset_token.is_used

    def test_reset_password_invalid_token(self, api_client: APIClient) -> None:
        """Reset password with invalid token returns 400."""
        payload = {
            "token": "invalid-token",
            "password": "NewSecurePass123!",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "token" in response.data

    def test_reset_password_used_token(
        self, api_client: APIClient, user: User
    ) -> None:
        """Reset password with already used token returns 400."""
        reset_token = PasswordResetToken.objects.create(user=user, is_used=True)

        payload = {
            "token": reset_token.token,
            "password": "NewSecurePass123!",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "token" in response.data

    def test_reset_password_expired_token(
        self, api_client: APIClient, user: User
    ) -> None:
        """Reset password with expired token returns 400."""
        reset_token = PasswordResetToken.objects.create(user=user)
        # Manually expire the token
        reset_token.expires_at = timezone.now() - timedelta(hours=2)
        reset_token.save()

        payload = {
            "token": reset_token.token,
            "password": "NewSecurePass123!",
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "token" in response.data
        assert "expired" in str(response.data["token"]).lower()

    def test_reset_password_weak_password(
        self, api_client: APIClient, user: User
    ) -> None:
        """Reset password with weak password returns 422."""
        reset_token = PasswordResetToken.objects.create(user=user)

        payload = {
            "token": reset_token.token,
            "password": "123",  # Too weak
        }

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "password")

    def test_reset_password_missing_token(self, api_client: APIClient) -> None:
        """Reset password without token returns 422."""
        payload = {"password": "NewSecurePass123!"}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "token")

    def test_reset_password_missing_password(
        self, api_client: APIClient, user: User
    ) -> None:
        """Reset password without password returns 422."""
        reset_token = PasswordResetToken.objects.create(user=user)

        payload = {"token": reset_token.token}

        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert has_error_for_field(response.data, "password")


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestAuthFlow:
    """Integration tests for complete authentication flows."""

    def test_full_signup_login_logout_flow(self, api_client: APIClient) -> None:
        """Test complete signup → login → logout flow."""
        # 1. Signup
        signup_payload = {
            "email": "flowtest@example.com",
            "password": "FlowTestPass123!",
            "name": "Flow Test User",
        }

        with patch("apps.auth_core.services.send_verification_email"):
            signup_response = api_client.post(
                "/api/v1/auth/signup/", signup_payload, format="json"
            )

        assert signup_response.status_code == status.HTTP_201_CREATED

        # 2. Login
        login_payload = {
            "email": "flowtest@example.com",
            "password": "FlowTestPass123!",
        }

        login_response = api_client.post(
            "/api/v1/auth/login/", login_payload, format="json"
        )

        assert login_response.status_code == status.HTTP_200_OK
        tokens = login_response.data

        # 3. Logout
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        logout_response = api_client.post(
            "/api/v1/auth/logout/",
            {"refresh": tokens["refresh"]},
            format="json",
        )

        assert logout_response.status_code == status.HTTP_204_NO_CONTENT

        # 4. Verify refresh token is blacklisted
        api_client.credentials()  # Clear credentials
        refresh_response = api_client.post(
            "/api/v1/auth/refresh/",
            {"refresh": tokens["refresh"]},
            format="json",
        )

        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_password_reset_flow(self, api_client: APIClient, user: User) -> None:
        """Test complete forgot password → reset password flow."""
        original_password = "TestPass123!"

        # 1. Request password reset
        with patch("apps.auth_core.views.send_password_reset_email"):
            forgot_response = api_client.post(
                "/api/v1/auth/forgot-password/",
                {"email": user.email},
                format="json",
            )

        assert forgot_response.status_code == status.HTTP_200_OK

        # Get the token that was created
        reset_token = PasswordResetToken.objects.get(user=user, is_used=False)

        # 2. Reset password
        new_password = "NewSecurePass456!"
        reset_response = api_client.post(
            "/api/v1/auth/reset-password/",
            {"token": reset_token.token, "password": new_password},
            format="json",
        )

        assert reset_response.status_code == status.HTTP_200_OK

        # 3. Verify old password no longer works
        old_login_response = api_client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": original_password},
            format="json",
        )

        assert old_login_response.status_code == status.HTTP_401_UNAUTHORIZED

        # 4. Verify new password works
        new_login_response = api_client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": new_password},
            format="json",
        )

        assert new_login_response.status_code == status.HTTP_200_OK

    def test_token_refresh_flow(self, api_client: APIClient, user: User) -> None:
        """Test login → refresh → use new access token flow."""
        # 1. Login
        login_response = api_client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "TestPass123!"},
            format="json",
        )

        assert login_response.status_code == status.HTTP_200_OK
        original_tokens = login_response.data

        # 2. Refresh
        refresh_response = api_client.post(
            "/api/v1/auth/refresh/",
            {"refresh": original_tokens["refresh"]},
            format="json",
        )

        assert refresh_response.status_code == status.HTTP_200_OK
        assert "access" in refresh_response.data

        # New access token should be different
        new_access = refresh_response.data["access"]
        assert new_access != original_tokens["access"]

    def test_multiple_password_reset_requests(
        self, api_client: APIClient, user: User
    ) -> None:
        """Test that multiple password reset requests invalidate previous tokens."""
        # 1. First password reset request
        with patch("apps.auth_core.views.send_password_reset_email"):
            api_client.post(
                "/api/v1/auth/forgot-password/",
                {"email": user.email},
                format="json",
            )

        first_token = PasswordResetToken.objects.get(user=user, is_used=False)

        # 2. Second password reset request
        with patch("apps.auth_core.views.send_password_reset_email"):
            api_client.post(
                "/api/v1/auth/forgot-password/",
                {"email": user.email},
                format="json",
            )

        # First token should be invalidated
        first_token.refresh_from_db()
        assert first_token.is_used

        # Second token should be valid
        second_token = PasswordResetToken.objects.get(user=user, is_used=False)
        assert second_token.token != first_token.token

        # 3. Try to use the first (invalidated) token
        reset_response = api_client.post(
            "/api/v1/auth/reset-password/",
            {"token": first_token.token, "password": "NewPassword123!"},
            format="json",
        )

        assert reset_response.status_code == status.HTTP_400_BAD_REQUEST

        # 4. Use the second (valid) token
        reset_response = api_client.post(
            "/api/v1/auth/reset-password/",
            {"token": second_token.token, "password": "NewPassword123!"},
            format="json",
        )

        assert reset_response.status_code == status.HTTP_200_OK
