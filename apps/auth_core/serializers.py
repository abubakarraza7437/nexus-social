"""
Auth Core — Serializers (backward-compat shim)
===============================================
Canonical location is now apps/auth_core/v1/serializers.py.

This module re-exports everything from v1 so existing code that imports
from ``apps.auth_core.serializers`` continues to work without modification.

NOTE: SIMPLE_JWT references this module directly for ``TOKEN_OBTAIN_SERIALIZER``:
    "apps.auth_core.serializers.CustomTokenObtainSerializer"
That setting stays valid because ``CustomTokenObtainSerializer`` is re-exported here.
"""
from .v1.serializers import (  # noqa: F401
    CustomTokenObtainSerializer,
    ForgotPasswordSerializer,
    LogoutSerializer,
    ResetPasswordSerializer,
    SignupSerializer,
)
