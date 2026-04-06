"""
Auth Core v1 — Views
======================
Moved here from apps/auth_core/views.py (the root file is now a
backward-compat shim that re-exports everything from this module).

No logic changes from the original — this is the canonical v1 contract.

POST /api/v1/auth/signup/              → SignupView
POST /api/v1/auth/login/               → LoginView
POST /api/v1/auth/refresh/             → RefreshView
POST /api/v1/auth/logout/              → LogoutView
POST /api/v1/auth/forgot-password/     → ForgotPasswordView
POST /api/v1/auth/reset-password/      → ResetPasswordView
GET  /api/v1/auth/verify-email/        → VerifyEmailView
POST /api/v1/auth/resend-verification/ → ResendVerificationEmailView
"""
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .. import services as auth_services
from ..services import create_user
from ..throttling import AuthRateThrottle, ResendVerificationThrottle
from .serializers import (
    ForgotPasswordSerializer,
    LogoutSerializer,
    ResetPasswordSerializer,
    SignupSerializer,
    DeleteAccountSerializer,
)


class SignupView(APIView):
    """
    Register a new user.

    POST /api/v1/auth/signup/
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


class LoginView(TokenObtainPairView):
    """
    Obtain a JWT access + refresh token pair.

    POST /api/v1/auth/login/
    Body: { email, password }
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]


class RefreshView(TokenRefreshView):
    """
    Rotate a JWT refresh token and return a new access token.

    POST /api/v1/auth/refresh/
    Body: { refresh }
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]


class LogoutView(APIView):
    """
    Blacklist the supplied refresh token, invalidating the session.

    POST /api/v1/auth/logout/
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


class ForgotPasswordView(APIView):
    """
    Initiate a password-reset flow. Returns 404 if the user does not exist
    or is inactive.

    POST /api/v1/auth/forgot-password/
    Body: { email }
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        from ..models import PasswordResetToken, User

        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response(
                {"detail": "User with this email does not exists."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.password_reset_tokens.filter(is_used=False).update(is_used=True)
        reset_token = PasswordResetToken.objects.create(user=user)
        auth_services.send_password_reset_email(user, reset_token.token)

        return Response(
            {"detail": "If that email is registered, you will receive a reset link."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    """
    Consume a password-reset token and update the user's password.

    POST /api/v1/auth/reset-password/
    Body: { token, password }
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        from ..models import PasswordResetToken

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


class VerifyEmailView(APIView):
    """
    Consume an email-verification token and mark the user as verified.

    GET /api/v1/auth/verify-email/?token=<token>
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def get(self, request):
        from ..models import EmailVerificationToken

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


class ResendVerificationEmailView(APIView):
    """
    Resend the email-verification link to an unverified user.

    POST /api/v1/auth/resend-verification/
    Body: { email }
    Always returns 200 to avoid leaking whether an email is registered.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ResendVerificationThrottle]

    def post(self, request):
        from ..models import EmailVerificationToken, User
        from ..services import send_verification_email

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
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            return _SAFE_RESPONSE

        if user.is_verified:
            return _SAFE_RESPONSE

        EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)
        new_token = EmailVerificationToken.objects.create(user=user)
        send_verification_email(user, new_token.token)

        return _SAFE_RESPONSE


class DeleteAccountView(APIView):
    """
    Delete the authenticated user's account.

    If the user is an owner of any organization, that organization is marked
    inactive, and other members are notified.
    If the user is a member of an organization, the owners are notified.

    DELETE /api/v1/auth/delete-account/
    Returns 204 on success.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = DeleteAccountSerializer

    def delete(self, request):
        from django.contrib.auth import get_user_model
        from apps.organizations.models import OrganizationMember
        from ..services import send_org_deleted_email, send_member_left_email
        from django_tenants.utils import schema_context
        from apps.organizations.models import Organization
        from django.db import connection, transaction

        User = get_user_model()
        user_obj = request.user

        if not user_obj or not user_obj.is_authenticated:
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            user = User.objects.get(id=user_obj.id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        user_id = user.id

        def _delete_user_manually(uid):
            from apps.auth_core.models import EmailVerificationToken, PasswordResetToken
            from apps.organizations.models import JoinRequest, OrganizationInvitation, OrganizationMember
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            from django.contrib.admin.models import LogEntry

            # Nullify foreign keys pointing to this user
            OrganizationMember.objects.filter(invited_by_id=uid).update(invited_by=None)
            OrganizationInvitation.objects.filter(invited_by_id=uid).update(invited_by=None)
            JoinRequest.objects.filter(reviewed_by_id=uid).update(reviewed_by=None)

            # Clear references in ALL tenant schemas BEFORE deleting user
            for t in Organization.objects.all():
                with schema_context(t.schema_name):
                    try:
                        with transaction.atomic():
                            # Use raw SQL to clear author_id to avoid "posts" relation error
                            with connection.cursor() as cursor:
                                cursor.execute("UPDATE posts SET author_id = NULL WHERE author_id = %s", [str(uid)])
                    except Exception:
                        pass

            # Switch to a known safe schema (public)
            connection.set_schema_to_public()

            # Delete child objects referencing this user
            JoinRequest.objects.filter(user_id=uid).delete()
            OutstandingToken.objects.filter(user_id=uid).delete()
            EmailVerificationToken.objects.filter(user_id=uid).delete()
            PasswordResetToken.objects.filter(user_id=uid).delete()
            OrganizationMember.objects.filter(user_id=uid).delete()
            LogEntry.objects.filter(user_id=uid).delete()

            # Now raw SQL delete the user
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE id = %s", [str(uid)])

        # Find organizations where this user is an owner
        owned_memberships = list(OrganizationMember.objects.filter(
            user=user, role=OrganizationMember.Role.OWNER
        ).select_related("organization"))

        for membership in owned_memberships:
            org = membership.organization
            org_name = org.name

            # Find all members except the owner
            other_memberships = list(OrganizationMember.objects.filter(
                organization=org
            ).exclude(user=user).select_related("user"))

            for other_mem in other_memberships:
                member_user = other_mem.user
                # Send email that organization is marked inactive/deleted
                send_org_deleted_email(member_user, org_name)
                # We do not delete the members' accounts or their memberships

            # Soft delete the organization by setting it to inactive
            org.is_active = False
            org.save(update_fields=["is_active"])

        # Notify owners of organizations where the user is just a member
        other_memberships_of_user = list(OrganizationMember.objects.filter(
            user=user
        ).exclude(role=OrganizationMember.Role.OWNER).select_related("organization"))

        for membership in other_memberships_of_user:
            org = membership.organization
            org_name = org.name

            owners = OrganizationMember.objects.filter(
                organization=org, role=OrganizationMember.Role.OWNER
            ).select_related("user")

            member_display_name = user.name or user.email
            for owner_mem in owners:
                send_member_left_email(owner_mem.user.email, member_display_name, org_name)

        # Delete the main user account using the manual helper
        _delete_user_manually(user_id)

        return Response(status=status.HTTP_204_NO_CONTENT)
