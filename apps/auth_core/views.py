"""
Auth Core — Views
=================
Covers the full authentication lifecycle:

  POST /auth/signup/           → SignupView
  POST /auth/login/            → LoginView        (JWT pair)
  POST /auth/refresh/          → RefreshView       (JWT refresh)
  POST /auth/logout/           → LogoutView        (blacklist refresh token)
  POST /auth/forgot-password/  → ForgotPasswordView
  POST /auth/reset-password/   → ResetPasswordView
"""
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    ForgotPasswordSerializer,
    LogoutSerializer,
    ResetPasswordSerializer,
    SignupSerializer,
)
from .services import (
    create_user_with_organization,
    send_password_reset_email,
)


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

class SignupView(APIView):
    """
    Register a new user and bootstrap their personal Organisation.

    POST /auth/signup/
    Body: { email, password, name }
    Returns 201 on success.
    """

    permission_classes = [AllowAny]
    serializer_class = SignupSerializer

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        create_user_with_organization(serializer.validated_data)
        return Response(
            {"detail": "Account created. Please verify your email."},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Login / Refresh
# ---------------------------------------------------------------------------

class LoginView(TokenObtainPairView):
    """
    Obtain a JWT access + refresh token pair.

    POST /auth/login/
    Body: { email, password }
    """

    permission_classes = [AllowAny]


class RefreshView(TokenRefreshView):
    """
    Rotate a JWT refresh token and return a new access token.

    POST /auth/refresh/
    Body: { refresh }
    """

    permission_classes = [AllowAny]


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class LogoutView(APIView):
    """
    Blacklist the supplied refresh token, invalidating the session.

    POST /auth/logout/
    Body: { refresh }
    Returns 204 on success.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        value = request.data.get("refresh")
        if not value:
            return Response(
                {"detail": "refresh token required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(value).blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------

class ForgotPasswordView(APIView):
    """
    Initiate a password-reset flow.  Always returns 200 to avoid leaking
    whether an email address is registered.

    POST /auth/forgot-password/
    Body: { email }
    """

    permission_classes = [AllowAny]
    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        from apps.auth_core.models import PasswordResetToken, User

        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            # Do not reveal whether the email exists.
            return Response(
                {
                    "detail": (
                        "If that email is registered, "
                        "you will receive a reset link."
                    )
                },
                status=status.HTTP_200_OK,
            )

        # Invalidate any prior unused tokens.
        user.password_reset_tokens.filter(is_used=False).update(is_used=True)

        # Create a fresh token and (mock) send it.
        reset_token = PasswordResetToken.objects.create(user=user)
        send_password_reset_email(user, reset_token.token)

        return Response(
            {
                "detail": (
                    "If that email is registered, "
                    "you will receive a reset link."
                )
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Reset Password
# ---------------------------------------------------------------------------

class ResetPasswordView(APIView):
    """
    Consume a password-reset token and update the user's password.

    POST /auth/reset-password/
    Body: { token, password }
    """

    permission_classes = [AllowAny]
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        from apps.auth_core.models import PasswordResetToken

        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_value = serializer.validated_data["token"]
        new_password = serializer.validated_data["password"]

        try:
            reset_token = PasswordResetToken.objects.get(
                token=token_value,
                is_used=False,
            )
        except PasswordResetToken.DoesNotExist:
            return Response(
                {"token": ["Invalid or expired token."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if reset_token.is_expired:
            return Response(
                {"token": ["Token has expired."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = reset_token.user
        user.set_password(new_password)
        user.save(update_fields=["password"])

        reset_token.is_used = True
        reset_token.save(update_fields=["is_used"])

        return Response(
            {"detail": "Password updated successfully."},
            status=status.HTTP_200_OK,
        )
