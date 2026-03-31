"""
Tests for health and readiness probes.
"""
import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_health_check(client: Client) -> None:
    """The liveness probe should always return 200 OK."""
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
