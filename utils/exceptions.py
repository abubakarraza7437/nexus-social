"""
Utils — Custom DRF Exception Handler
======================================
Standardises every error response to the envelope format:

    {
        "data":   null,
        "meta":   {},
        "errors": [
            {"field": "email",   "message": "Enter a valid email address."},
            {"field": "non_field_errors", "message": "..."}
        ]
    }

This means the frontend always knows where to look for errors and never
has to special-case DRF's varying error shapes.
"""
import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def _flatten_errors(detail: Any, field: str = "non_field_errors") -> list[dict]:
    """
    Recursively flatten DRF's nested error detail into a flat list of
    ``{"field": ..., "message": ...}`` dicts.
    """
    errors: list[dict] = []

    if isinstance(detail, list):
        for item in detail:
            errors.extend(_flatten_errors(item, field))
    elif isinstance(detail, dict):
        for key, value in detail.items():
            errors.extend(_flatten_errors(value, key))
    else:
        errors.append({"field": field, "message": str(detail)})

    return errors


def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    Drop-in replacement for DRF's default exception handler.
    Registered in settings.REST_FRAMEWORK["EXCEPTION_HANDLER"].
    """
    # Let DRF convert Django's Http404 / PermissionDenied first.
    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled server error — let Django's 500 handler take it.
        logger.exception("Unhandled exception in view", exc_info=exc)
        return None

    # ------------------------------------------------------------------ #
    # Normalise to envelope format                                         #
    # ------------------------------------------------------------------ #
    if isinstance(exc, ValidationError):
        errors = _flatten_errors(exc.detail)
        http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, (Http404,)):
        errors = [{"field": "non_field_errors", "message": "Not found."}]
        http_status = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, PermissionDenied):
        errors = [{"field": "non_field_errors", "message": "Permission denied."}]
        http_status = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, APIException):
        errors = _flatten_errors(exc.detail)
        http_status = exc.status_code
    else:
        errors = [{"field": "non_field_errors", "message": "An unexpected error occurred."}]
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    response.data = {
        "data": None,
        "meta": {},
        "errors": errors,
    }
    response.status_code = http_status
    return response
