"""
Auth Core — Views (backward-compat shim)
=========================================
Canonical location is now apps/auth_core/v1/views.py.

This module re-exports everything from v1 so existing code that imports
from ``apps.auth_core.views`` continues to work without modification.
"""
from .services import send_password_reset_email  # noqa: F401
from .v1.views import (  # noqa: F401
    ForgotPasswordView,
    LoginView,
    LogoutView,
    RefreshView,
    ResendVerificationEmailView,
    ResetPasswordView,
    SignupView,
    VerifyEmailView,
)
