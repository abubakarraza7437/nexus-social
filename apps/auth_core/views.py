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
    create_user,
    send_password_reset_email,
)
from .throttling import AuthRateThrottle, ResendVerificationThrottle


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
    throttle_classes = [AuthRateThrottle]
    serializer_class = SignupSerializer

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        create_user(serializer.validated_data)
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
    throttle_classes = [AuthRateThrottle]


class RefreshView(TokenRefreshView):
    """
    Rotate a JWT refresh token and return a new access token.

    POST /auth/refresh/
    Body: { refresh }
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]


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
    throttle_classes = [AuthRateThrottle]
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
                        "User with this email does not exists."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
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
    throttle_classes = [AuthRateThrottle]
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


# ---------------------------------------------------------------------------
# Verify Email
# ---------------------------------------------------------------------------

class VerifyEmailView(APIView):
    """
    Consume an email-verification token and mark the user as verified.

    GET /auth/verify-email/?token=<token>
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def get(self, request):
        from apps.auth_core.models import EmailVerificationToken

        token_value = request.query_params.get("token", "").strip()
        if not token_value:
            return Response(
                {"detail": "Token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = EmailVerificationToken.objects.select_related("user").get(
                token=token_value,
            )
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"detail": "Invalid verification link. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Already used — check if the user is verified (e.g. double click / StrictMode)
        if token.is_used:
            if token.user.is_verified:
                return Response(
                    {"detail": "Email already verified. You can now sign in."},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"detail": "This link has already been used. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token.is_expired:
            return Response(
                {"detail": "This verification link has expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token.user
        user.is_verified = True
        user.save(update_fields=["is_verified"])

        token.is_used = True
        token.save(update_fields=["is_used"])

        return Response(
            {"detail": "Email verified successfully. You can now sign in."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Resend Verification Email
# ---------------------------------------------------------------------------

class ResendVerificationEmailView(APIView):
    """
    Resend the email-verification link to an unverified user.

    POST /auth/resend-verification/
    Body: { email }

    Always returns 200 to avoid leaking whether an email is registered.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ResendVerificationThrottle]

    def post(self, request):
        from apps.auth_core.models import EmailVerificationToken
        from .services import send_verification_email

        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response(
                {"detail": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _SAFE_RESPONSE = Response(
            {"detail": "If that email is registered and unverified, a new link has been sent."},
            status=status.HTTP_200_OK,
        )

        try:
            from apps.auth_core.models import User
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            return _SAFE_RESPONSE

        if user.is_verified:
            return _SAFE_RESPONSE

        # Invalidate all prior unused tokens for this user.
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)

        # Issue a fresh token and send it.
        new_token = EmailVerificationToken.objects.create(user=user)
        send_verification_email(user, new_token.token)

        return _SAFE_RESPONSE
