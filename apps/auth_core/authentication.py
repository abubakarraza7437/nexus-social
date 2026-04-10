from collections import namedtuple

from django_tenants.utils import get_public_schema_name
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

SimpleMembership = namedtuple("SimpleMembership", ["role", "org_id"])


class JWTAuthenticationWithContext(JWTAuthentication):

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result

        tenant = getattr(request, "tenant", None)
        public_schema = get_public_schema_name()  # typically "public"

        if tenant is not None and tenant.schema_name != public_schema:
            org_id_in_token = validated_token.get("org")

            if not org_id_in_token:
                raise AuthenticationFailed(
                    "Token has no organization claim. "
                    "Log in again to obtain an org-scoped token."
                )

            if str(tenant.id) != str(org_id_in_token):
                raise AuthenticationFailed(
                    "Token is not valid for this organization."
                )

        # ------------------------------------------------------------------ #
        # Attach context to request                                           #
        # ------------------------------------------------------------------ #
        role = validated_token.get("role")
        org_id = validated_token.get("org")

        if role and org_id:
            request.membership = SimpleMembership(role=role, org_id=org_id)

        # Alias request.tenant as request.org for serializer / view code.
        if tenant is not None:
            request.org = tenant

        return user, validated_token
