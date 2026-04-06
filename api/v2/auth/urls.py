"""
Auth v2 — URL patterns.

Mounted at /api/v2/auth/ via api/v2/urls.py.

Endpoints with v2 implementations use the new views defined in this package.
All other endpoints re-use the v1 view classes imported from
``apps.auth_core.views`` via ``api.v2.auth.views``.
"""
from django.urls import path

from .views import (
    ForgotPasswordView,
    LoginViewV2,
    LogoutView,
    RefreshView,
    ResendVerificationEmailView,
    ResetPasswordView,
    SignupViewV2,
    VerifyEmailView,
)

urlpatterns = [
    # v2-specific implementations
    path("signup/", SignupViewV2.as_view(), name="v2-auth-signup"),
    path("login/", LoginViewV2.as_view(), name="v2-auth-login"),

    # Unchanged from v1 — same view class, new URL registration
    path("refresh/", RefreshView.as_view(), name="v2-auth-token-refresh"),
    path("logout/", LogoutView.as_view(), name="v2-auth-logout"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="v2-auth-forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="v2-auth-reset-password"),
    path("verify-email/", VerifyEmailView.as_view(), name="v2-auth-verify-email"),
    path("resend-verification/", ResendVerificationEmailView.as_view(), name="v2-auth-resend-verification"),
]
