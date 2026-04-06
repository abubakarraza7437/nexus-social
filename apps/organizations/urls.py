"""
Organizations — URLs (backward-compat shim)
============================================
Canonical location is now apps/organizations/v1/urls.py.
Re-exports app_name and urlpatterns from v1.
"""
from .v1.urls import app_name, urlpatterns  # noqa: F401
