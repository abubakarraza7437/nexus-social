# Generated migration — OrganizationInvitation model.

import django.db.models.deletion
import secrets
import uuid

from django.conf import settings
from django.db import migrations, models

import apps.organizations.models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_tenants"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationInvitation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("member", "Member"),
                        ],
                        default="member",
                        max_length=20,
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
                        default=apps.organizations.models._invitation_expiry
                    ),
                ),
                ("is_used", models.BooleanField(default=False)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invitations",
                        to="organizations.organization",
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_org_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "organization_invitations",
            },
        ),
        migrations.AddIndex(
            model_name="organizationinvitation",
            index=models.Index(
                fields=["token"],
                name="org_inv_token_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationinvitation",
            index=models.Index(
                fields=["organization", "email"],
                name="org_inv_org_email_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationinvitation",
            index=models.Index(
                fields=["organization", "is_used"],
                name="org_inv_org_used_idx",
            ),
        ),
    ]
