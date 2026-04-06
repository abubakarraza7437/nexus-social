"""
Auth v2 — Views
================
Extends v1 auth views with enriched responses.

v2 changes
----------
``LoginViewV2``
    Login response embeds a ``user`` object alongside the JWT tokens.
    Clients no longer need a separate ``/me`` call after login.

    v1 response shape:
        { "access": "...", "refresh": "..." }

    v2 response shape:
        {
          "access": "...",
          "refresh": "...",
          "user": { "id", "email", "name", "avatar_url", "mfa_enabled", "is_verified" }
        }

``SignupViewV2``
    Signup response includes the created user's profile.

    v1 response shape:
        { "detail": "Account created. Please verify your email." }

    v2 response shape:
        {
          "detail": "Account created. Please verify your email.",
          "user": { "id", "email", "name", "avatar_url", "mfa_enabled", "is_verified" }
        }

Unchanged endpoints (re-exported from v1)
------------------------------------------
All other auth endpoints are identical in v1 and v2:
  - RefreshView            POST /auth/refresh/
  - LogoutView             POST /auth/logout/
  - ForgotPasswordView     POST /auth/forgot-password/
  - ResetPasswordView      POST /auth/reset-password/
  - VerifyEmailView        GET  /auth/verify-email/
  - ResendVerificationView POST /auth/resend-verification/
"""
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.auth_core.services import create_user
from apps.auth_core.throttling import AuthRateThrottle

# Re-export unchanged v1 views — v2 urls.py imports everything from here.
from apps.auth_core.views import (  # noqa: F401 — intentional re-export
    ForgotPasswordView,
    LogoutView,
    RefreshView,
    ResendVerificationEmailView,
    ResetPasswordView,
    VerifyEmailView,
)

from .serializers import (
    LoginResponseSerializer,
    SignupResponseSerializer,
    SignupSerializer,
    UserProfileSerializer,
)

User = get_user_model()


class LoginViewV2(TokenObtainPairView):
    """
    POST /api/v2/auth/login/

    Identical to v1 but the response body includes a ``user`` object, removing
    the extra profile fetch that v1 clients must perform after login.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(responses=LoginResponseSerializer)
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            # The parent serializer already validated credentials; the user
            # must exist.  We look them up by the submitted email.
            email = request.data.get("email", "")
            try:
                user = User.objects.get(email__iexact=email)
                response.data["user"] = UserProfileSerializer(user).data
            except User.DoesNotExist:
                pass  # Guard only — token generation above already succeeded.

        return response


class SignupViewV2(APIView):
    """
    POST /api/v2/auth/signup/

    Identical validation to v1 but the 201 response now returns the newly
    created user's profile, so clients can pre-populate the UI without waiting
    for a separate profile request.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = SignupSerializer

    @extend_schema(
        request=SignupSerializer,
        responses=SignupResponseSerializer,
    )
    def post(self, request, *args, **kwargs):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = create_user(serializer.validated_data)
        return Response(
            {
                "detail": "Account created. Please verify your email.",
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )
