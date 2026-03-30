"""
Root conftest — pytest configuration for the entire test suite.
"""
import django
import pytest
from django.conf import settings


def pytest_configure(config) -> None:
    """Called before Django is set up."""
    settings.DATABASES["default"]["CONN_MAX_AGE"] = 0   # No persistent conns in tests


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the cache between tests to prevent state leakage."""
    from django.core.cache import cache
    yield
    cache.clear()
