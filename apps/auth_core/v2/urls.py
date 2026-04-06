"""
Auth Core v2 — URL patterns.
Mounted at /api/v2/auth/ via api/v2/urls.py.
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

app_name = "auth_v2"

urlpatterns = [
    # v2-specific implementations
    path("signup/", SignupViewV2.as_view(), name="signup"),
    path("login/", LoginViewV2.as_view(), name="login"),
    # Unchanged from v1
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
    path("resend-verification/", ResendVerificationEmailView.as_view(), name="resend_verification"),
]
