"""
Management command: create_public_tenant
========================================
Creates the required django-tenants "public" Organization + Domain row so
that requests to the configured hostname(s) resolve to the public schema
(admin, auth, OpenAPI docs, etc.).

Run once after the initial migrate_schemas --shared:

    python manage.py create_public_tenant
    python manage.py create_public_tenant --domain api.example.com

The public schema is special: PostgreSQL always has one, so we must NOT let
TenantMixin attempt CREATE SCHEMA public.  We bypass this by disabling
auto_create_schema on the class before any INSERT, then restoring it.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed the public tenant (schema_name='public') and its domain."

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            default="localhost",
            help="Hostname to register as the primary domain (default: localhost).",
        )
        parser.add_argument(
            "--name",
            default="Public",
            help="Display name for the public organization (default: Public).",
        )

    def handle(self, *args, **options):
        from apps.organizations.models import Domain, Organization

        domain_name: str = options["domain"]
        org_name: str = options["name"]

        # Disable schema creation BEFORE any INSERT so TenantMixin.save() does
        # not attempt CREATE SCHEMA public (which always already exists).
        original_auto_create = Organization.auto_create_schema
        Organization.auto_create_schema = False
        try:
            org, org_created = Organization.objects.get_or_create(
                schema_name="public",
                defaults={
                    "name": org_name,
                    "slug": "public",
                    "is_active": True,
                },
            )
        finally:
            Organization.auto_create_schema = original_auto_create

        if org_created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created public Organization "{org.name}" (schema=public).'
                )
            )
        else:
            self.stdout.write(f'Public Organization already exists: "{org.name}".')

        domain, dom_created = Domain.objects.get_or_create(
            domain=domain_name,
            defaults={"tenant": org, "is_primary": True},
        )

        if dom_created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Registered domain "{domain_name}" → public schema.'
                )
            )
        else:
            self.stdout.write(f'Domain "{domain_name}" already registered.')

        self.stdout.write(self.style.SUCCESS("Public tenant ready."))
