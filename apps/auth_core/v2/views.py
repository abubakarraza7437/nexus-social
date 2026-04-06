"""
Auth Core v2 — Views
======================
Extends v1 views with enriched response payloads.

v2 changes
----------
``LoginViewV2``
    Response embeds a ``user`` object alongside the JWT tokens, removing
    the extra /me fetch that v1 clients perform after login.

    v1:  { "access": "...", "refresh": "..." }
    v2:  { "access": "...", "refresh": "...", "user": { id, email, name, ... } }

``SignupViewV2``
    Response includes the newly created user's profile.

    v1:  { "detail": "Account created. Please verify your email." }
    v2:  { "detail": "...", "user": { id, email, name, ... } }

Unchanged endpoints
-------------------
All other auth endpoints are identical in v1 and v2.  They are re-exported
from v1 here so v2/urls.py has a single import surface.
"""
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from ..services import create_user
from ..throttling import AuthRateThrottle

# Re-export v1 views that have no changes in v2.
from ..v1.views import (  # noqa: F401
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

    Identical validation to v1.  Response body now includes a ``user`` object
    so clients do not need a separate profile request after login.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(responses=LoginResponseSerializer)
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            # Credentials already validated by the parent serializer.
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

    Identical validation to v1.  Response now includes the created user's
    profile so the UI can be pre-populated without an extra /me call.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = SignupSerializer

    @extend_schema(request=SignupSerializer, responses=SignupResponseSerializer)
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
