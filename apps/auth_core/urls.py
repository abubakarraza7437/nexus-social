"""
Auth Core — URL patterns.
"""
from django.urls import path

from .views import (
    ForgotPasswordView,
    LoginView,
    LogoutView,
    RefreshView,
    ResetPasswordView,
    SignupView,
)

app_name = "auth"

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
]
