"""
Auth Core — URLs (backward-compat shim)
========================================
Canonical location is now apps/auth_core/v1/urls.py.
This module re-exports app_name and urlpatterns from v1.
"""
from .v1.urls import app_name, urlpatterns  # noqa: F401
