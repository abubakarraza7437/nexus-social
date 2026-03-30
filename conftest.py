"""
Root conftest — pytest configuration for the entire test suite.
"""

from django.conf import settings

import pytest


def pytest_configure(config) -> None:
    """Called before Django is set up."""
    # No persistent conns in tests
    settings.DATABASES["default"]["CONN_MAX_AGE"] = 0


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the cache between tests to prevent state leakage."""
    from django.core.cache import cache

    yield
    cache.clear()
