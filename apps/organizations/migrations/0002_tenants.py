"""
Migration: integrate django-tenants into the organizations app.

Changes:
  Organization    — add schema_name (TenantMixin requirement)
  Domain          — new model (DomainMixin; maps hostnames → tenant)
  OrganizationMember — rename joined_at → created_at; update role choices/default
"""
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def _backfill_schema_name(apps, schema_editor):
    """
    Populate schema_name from slug for any rows that exist.
    Slugs use hyphens; PostgreSQL schema names cannot, so we replace them.
    """
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.all():
        org.schema_name = org.slug.replace("-", "_")
        org.save(update_fields=["schema_name"])


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------
        # 1. Add schema_name as nullable first so existing rows don't error.
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="organization",
            name="schema_name",
            field=models.CharField(max_length=63, null=True),
        ),

        # ------------------------------------------------------------------
        # 2. Backfill schema_name from slug for any pre-existing rows.
        # ------------------------------------------------------------------
        migrations.RunPython(_backfill_schema_name, reverse_code=_noop),

        # ------------------------------------------------------------------
        # 3. Make schema_name NOT NULL and UNIQUE.
        # ------------------------------------------------------------------
        migrations.AlterField(
            model_name="organization",
            name="schema_name",
            field=models.CharField(max_length=63, unique=True),
        ),

        # ------------------------------------------------------------------
        # 4. Domain model (required by django-tenants TENANT_DOMAIN_MODEL).
        #    DomainMixin contributes: domain (unique), tenant FK, is_primary.
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Domain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("domain", models.CharField(db_index=True, max_length=253, unique=True)),
                ("is_primary", models.BooleanField(db_index=True, default=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domains",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Domain",
                "verbose_name_plural": "Domains",
                "db_table": "organization_domains",
            },
        ),

        # ------------------------------------------------------------------
        # 5. OrganizationMember: rename joined_at → created_at.
        # ------------------------------------------------------------------
        migrations.RenameField(
            model_name="organizationmember",
            old_name="joined_at",
            new_name="created_at",
        ),

        # ------------------------------------------------------------------
        # 6. OrganizationMember: update role choices and default
        #    (editor/viewer → member; default viewer → member).
        # ------------------------------------------------------------------
        migrations.AlterField(
            model_name="organizationmember",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("admin", "Admin"),
                    ("member", "Member"),
                ],
                default="member",
                max_length=20,
            ),
        ),
    ]