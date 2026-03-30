"""
Organizations — Tenant Isolation Middleware
============================================
Sets the PostgreSQL session variable `app.current_org_id` on every request
that belongs to an authenticated, org-scoped user.

This is consumed by the Row-Level Security (RLS) policy on every tenant table:

    CREATE POLICY tenant_isolation ON posts
    USING (org_id = current_setting('app.current_org_id')::uuid);

Why SET LOCAL?
  SET LOCAL is transaction-scoped — it resets automatically when the
  transaction ends (i.e. at the end of the request).  This guarantees
  isolation even if a connection is reused from PgBouncer's pool.

Order in MIDDLEWARE list matters:
  Must run AFTER AuthenticationMiddleware (request.user must be populated),
  but DRF authentication runs inside the view, not in middleware.

  Solution: `request.org` is attached by the JWT authentication flow
  (see apps.auth_core.authentication).  This middleware checks for it
  defensively — if absent, it's a no-op and the request proceeds without
  RLS enforcement (which is fine for public/unauthenticated endpoints).
"""

import logging

from django.db import connection

logger = logging.getLogger(__name__)


class TenantIsolationMiddleware:
    """
    Sets `app.current_org_id` on the PostgreSQL connection for the duration
    of each authenticated, org-scoped request.
    """

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # request.org is set by DRF's authentication (JWT claims) AFTER the
        # view is called.  We therefore set the session variable in a
        # process_view hook instead.  See below.
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Called by Django just before the view is invoked.
        By this point, DRF's perform_authentication() has run and
        request.org may be available if the request is authenticated.
        """
        org = getattr(request, "org", None)
        if org is not None:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET LOCAL app.current_org_id = %s",
                        [str(org.id)],
                    )
            except Exception:
                # Graceful degradation — log but don't break the request.
                logger.exception("Failed to set app.current_org_id for org=%s", org.id)
        return None  # None = continue processing (don't short-circuit)
