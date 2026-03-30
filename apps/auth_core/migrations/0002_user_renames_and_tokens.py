"""
Migration: rename User fields and add token models.

Changes:
  User                   — full_name → name, is_email_verified → is_verified
  EmailVerificationToken — new model (24-hour single-use email verification)
  PasswordResetToken     — new model (1-hour single-use password reset)
"""
import apps.auth_core.models
import django.db.models.deletion
import secrets
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth_core", "0001_initial"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # User field renames
        # ------------------------------------------------------------------
        migrations.RenameField(
            model_name="user",
            old_name="full_name",
            new_name="name",
        ),
        migrations.RenameField(
            model_name="user",
            old_name="is_email_verified",
            new_name="is_verified",
        ),

        # ------------------------------------------------------------------
        # EmailVerificationToken
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="EmailVerificationToken",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_verification_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "token",
                    models.CharField(
                        default=secrets.token_urlsafe,
                        max_length=64,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "expires_at",
                    models.DateTimeField(
                        default=apps.auth_core.models._email_token_expiry,
                    ),
                ),
                ("is_used", models.BooleanField(default=False)),
            ],
            options={
                "verbose_name": "Email Verification Token",
                "verbose_name_plural": "Email Verification Tokens",
                "db_table": "email_verification_tokens",
            },
        ),
        migrations.AddIndex(
            model_name="emailverificationtoken",
            index=models.Index(fields=["token"], name="email_ver_token_idx"),
        ),
        migrations.AddIndex(
            model_name="emailverificationtoken",
            index=models.Index(fields=["user", "is_used"], name="email_ver_user_used_idx"),
        ),

        # ------------------------------------------------------------------
        # PasswordResetToken
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="PasswordResetToken",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_reset_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "token",
                    models.CharField(
                        default=secrets.token_urlsafe,
                        max_length=64,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "expires_at",
                    models.DateTimeField(
                        default=apps.auth_core.models._reset_token_expiry,
                    ),
                ),
                ("is_used", models.BooleanField(default=False)),
            ],
            options={
                "verbose_name": "Password Reset Token",
                "verbose_name_plural": "Password Reset Tokens",
                "db_table": "password_reset_tokens",
            },
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(fields=["token"], name="pwd_reset_token_idx"),
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(fields=["user", "is_used"], name="pwd_reset_user_used_idx"),
        ),
    ]