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
                logger.exception(
                    "Failed to set app.current_org_id for org=%s", org.id
                )
        return None   # None = continue processing (don't short-circuit)
