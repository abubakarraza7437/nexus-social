import pytest
from django.conf import settings


def pytest_configure(config) -> None:
    """Called before Django is set up."""
    settings.DATABASES["default"]["CONN_MAX_AGE"] = 0   # No persistent conns in tests

    # Disable Silk profiling middleware during tests to avoid missing table errors.
    # Silk is only useful in development for interactive profiling, not in tests.
    if "silk" in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS.remove("silk")
    settings.MIDDLEWARE = [
        m for m in settings.MIDDLEWARE if not m.startswith("silk.")
    ]


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the cache between tests to prevent state leakage."""
    from django.core.cache import cache
    yield
    cache.clear()


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """
    Create the public tenant after the test database is set up.
    This is required for django-tenants to resolve requests to the public schema.
    """
    with django_db_blocker.unblock():
        from apps.organizations.models import Domain, Organization

        # Disable auto schema creation for the public tenant
        original_auto_create = Organization.auto_create_schema
        Organization.auto_create_schema = False
        try:
            org, _ = Organization.objects.get_or_create(
                schema_name="public",
                defaults={
                    "name": "Public",
                    "slug": "public",
                    "is_active": True,
                },
            )
        finally:
            Organization.auto_create_schema = original_auto_create

        # Register localhost domain for the public tenant
        Domain.objects.get_or_create(
            domain="localhost",
            defaults={"tenant": org, "is_primary": True},
        )
        # Also register testserver (used by Django test client)
        Domain.objects.get_or_create(
            domain="testserver",
            defaults={"tenant": org, "is_primary": False},
        )
