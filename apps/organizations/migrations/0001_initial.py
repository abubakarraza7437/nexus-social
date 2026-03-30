import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
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
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(unique=True)),
                (
                    "plan",
                    models.CharField(
                        choices=[
                            ("free", "Free"),
                            ("pro", "Pro ($29/mo)"),
                            ("business", "Business ($99/mo)"),
                            ("enterprise", "Enterprise (Custom)"),
                        ],
                        default="free",
                        max_length=20,
                    ),
                ),
                ("plan_limits", models.JSONField(default=dict)),
                (
                    "billing_customer_id",
                    models.CharField(blank=True, max_length=100),
                ),
                (
                    "subscription_id",
                    models.CharField(blank=True, max_length=100),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("settings", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Organization",
                "verbose_name_plural": "Organizations",
                "db_table": "organizations",
            },
        ),
        migrations.CreateModel(
            name="OrganizationMember",
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
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("editor", "Editor"),
                            ("viewer", "Viewer"),
                        ],
                        default="viewer",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("notification_settings", models.JSONField(default=dict)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="organizations.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_members",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Organization Member",
                "verbose_name_plural": "Organization Members",
                "db_table": "organization_members",
            },
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(fields=["slug"], name="organizations_slug_idx"),
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(
                fields=["billing_customer_id"],
                name="organizations_billing_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(
                fields=["is_active", "plan"],
                name="organizations_active_plan_idx",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="organizationmember",
            unique_together={("organization", "user")},
        ),
        migrations.AddIndex(
            model_name="organizationmember",
            index=models.Index(
                fields=["organization", "role"],
                name="org_members_org_role_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationmember",
            index=models.Index(
                fields=["user", "is_active"],
                name="org_members_user_active_idx",
            ),
        ),
    ]
