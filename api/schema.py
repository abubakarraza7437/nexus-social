"""
API Schema Preprocessing Hooks
================================
drf-spectacular preprocessing hooks that filter the generated OpenAPI schema
to a specific API version.  Each hook is referenced by name in
``SpectacularAPIView.as_view(custom_settings={...})`` within ``socialos/urls.py``.

How it works
------------
drf-spectacular calls each preprocessing hook with the full list of
``(path, path_regex, method, callback)`` tuples before schema generation.
Returning a filtered subset restricts the schema to matching endpoints only.

Registration
------------
The hooks are referenced as dotted import paths in the ``custom_settings``
kwarg passed to ``SpectacularAPIView.as_view()`` in the URL configuration —
no changes to ``SPECTACULAR_SETTINGS`` are needed.
"""
from typing import Any


def _filter_by_prefix(endpoints: list, prefix: str) -> list:
    return [
        (path, path_regex, method, callback)
        for path, path_regex, method, callback in endpoints
        if path.startswith(prefix)
    ]


def filter_v1_endpoints(endpoints: list, **kwargs: Any) -> list:
    """Retain only /api/v1/ endpoints."""
    return _filter_by_prefix(endpoints, "/api/v1/")


def filter_v2_endpoints(endpoints: list, **kwargs: Any) -> list:
    """Retain only /api/v2/ endpoints."""
    return _filter_by_prefix(endpoints, "/api/v2/")
