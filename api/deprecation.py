"""
API Deprecation Utilities
==========================
Signals to API consumers that an endpoint or version is scheduled for removal.

Two mechanisms are provided:

1. ``DeprecationWarningMixin`` — a DRF view mixin that injects standard HTTP
   deprecation headers into every response.

2. ``deprecation_warning`` — a decorator for function-based views with the
   same effect.

HTTP headers emitted
--------------------
  ``Deprecation: true``
      RFC 8594 — indicates the resource is deprecated.

  ``Sunset: <RFC 7231 date>``
      RFC 8594 — the date after which the resource will be unavailable.
      Only emitted when ``deprecation_date`` is provided.

  ``Link: <url>; rel="successor-version"``
      RFC 8288 — points clients to the replacement endpoint.
      Only emitted when ``successor_url`` is provided.

Usage (class-based view mixin)
------------------------------
    class LoginViewV1(DeprecationWarningMixin, TokenObtainPairView):
        deprecation_date = "2027-01-01"
        successor_url = "/api/v2/auth/login/"

Usage (function-based view decorator)
--------------------------------------
    @deprecation_warning(sunset_date="2027-01-01", successor_url="/api/v2/auth/login/")
    def login(request):
        ...
"""
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
    """
    DRF view mixin that injects deprecation headers into every response.

    Class attributes
    ----------------
    deprecation_date : str | None
        ISO-8601 date string (``"YYYY-MM-DD"``) of the planned sunset.
    successor_url : str | None
        Absolute path of the replacement endpoint, e.g. ``"/api/v2/auth/login/"``.
    """

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
    """
    Decorator for function-based views that emits deprecation headers.

    Parameters
    ----------
    sunset_date : str | None
        ISO-8601 date string of the planned sunset, e.g. ``"2027-01-01"``.
    successor_url : str | None
        Absolute path of the replacement endpoint.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)
            _attach_deprecation_headers(response, sunset_date, successor_url)
            return response
        return wrapper
    return decorator
