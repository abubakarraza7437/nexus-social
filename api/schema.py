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
