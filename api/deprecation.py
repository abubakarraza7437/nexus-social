import functools
from datetime import datetime

_HTTP_DATE_FORMAT = "%a, %d %b %Y 00:00:00 GMT"


def _attach_deprecation_headers(
    response,
    deprecation_date: str | None,
    successor_url: str | None,
) -> None:
    """Mutate *response* to carry standard deprecation headers."""
    response["Deprecation"] = "true"

    if deprecation_date:
        try:
            dt = datetime.strptime(deprecation_date, "%Y-%m-%d")
            response["Sunset"] = dt.strftime(_HTTP_DATE_FORMAT)
        except ValueError:
            pass  # Malformed date — skip rather than crash.

    if successor_url:
        response["Link"] = f'<{successor_url}>; rel="successor-version"'


class DeprecationWarningMixin:

    deprecation_date: str | None = None
    successor_url: str | None = None

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        _attach_deprecation_headers(response, self.deprecation_date, self.successor_url)
        return response


def deprecation_warning(
    sunset_date: str | None = None,
    successor_url: str | None = None,
):

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)
            _attach_deprecation_headers(response, sunset_date, successor_url)
            return response
        return wrapper
    return decorator
