"""
Auth Core — URL patterns.
Full view implementations will be added in the auth feature section.
"""
from django.http import JsonResponse
from django.urls import path
from django.views import View
from rest_framework_simplejwt.views import TokenRefreshView


class _PlaceholderView(View):
    """Returns 501 until the real view is wired up."""
    endpoint_name: str = ""

    def dispatch(self, request, *args, **kwargs):
        return JsonResponse(
            {"detail": f"Endpoint '{self.endpoint_name}' not yet implemented."},
            status=501,
        )


def _stub(name: str):
    return type(f"{name}View", (_PlaceholderView,), {"endpoint_name": name}).as_view()


app_name = "auth"

urlpatterns = [
    # JWT
    path("token/", _stub("token_obtain"), name="token_obtain"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/blacklist/", _stub("token_blacklist"), name="token_blacklist"),

    # Account
    path("register/", _stub("register"), name="register"),
    path("password/change/", _stub("password_change"), name="password_change"),

    # MFA
    path("mfa/enable/", _stub("mfa_enable"), name="mfa_enable"),
    path("mfa/verify/", _stub("mfa_verify"), name="mfa_verify"),

    # Social OAuth
    path("oauth/<str:platform>/", _stub("oauth_init"), name="oauth_init"),
    path("oauth/<str:platform>/callback/", _stub("oauth_callback"), name="oauth_callback"),
]
