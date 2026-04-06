"""
Auth Core v1 — URL patterns.
Mounted at /api/v1/auth/ via api/v1/urls.py.
"""
from django.urls import path

from .views import (
    ForgotPasswordView,
    LoginView,
    LogoutView,
    RefreshView,
    ResendVerificationEmailView,
    ResetPasswordView,
    SignupView,
    VerifyEmailView,
    DeleteAccountView,
)

app_name = "auth"

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
    path("resend-verification/", ResendVerificationEmailView.as_view(), name="resend_verification"),
    path("delete-account/", DeleteAccountView.as_view(), name="delete_account"),
]
