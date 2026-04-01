# Generated migration for JoinRequest model

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0003_organization_invitation"),
    ]

    operations = [
        migrations.CreateModel(
            name="JoinRequest",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("expired", "Expired"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "message",
                    models.TextField(blank=True, max_length=500),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "rejection_reason",
                    models.TextField(blank=True, max_length=500),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "expires_at",
                    models.DateTimeField(blank=True, default=None, null=True),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="join_requests",
                        to="organizations.organization",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_join_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="join_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Join Request",
                "verbose_name_plural": "Join Requests",
                "db_table": "organization_join_requests",
            },
        ),
        migrations.AddIndex(
            model_name="joinrequest",
            index=models.Index(
                fields=["organization", "status"],
                name="organizatio_organiz_a1b2c3_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="joinrequest",
            index=models.Index(
                fields=["user", "status"],
                name="organizatio_user_id_d4e5f6_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="joinrequest",
            index=models.Index(
                fields=["status", "created_at"],
                name="organizatio_status_g7h8i9_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="joinrequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("user", "organization"),
                name="unique_pending_join_request",
            ),
        ),
    ]
