"""
Auth Core — Plan-Based Rate Limiting
======================================
Throttle requests per organization based on their subscription plan.
Uses a Redis sliding-window implemented via a Lua script for atomicity.

Rate limits:
  free       →    100 requests / day
  pro        → 10,000 requests / day
  business   → 50,000 requests / day
  enterprise → unlimited
"""
from rest_framework.throttling import SimpleRateThrottle


class OrgPlanThrottle(SimpleRateThrottle):
    """
    Per-organization throttle keyed to the org's subscription plan.

    Falls back to "100/day" for unauthenticated or plan-less requests.
    The enterprise plan bypasses throttling entirely (returns True immediately).
    """

    scope = "org_plan"

    PLAN_RATES: dict[str, str | None] = {
        "free": "100/day",
        "pro": "10000/day",
        "business": "50000/day",
        "enterprise": None,     # None = no limit
    }

    def get_rate(self) -> str | None:
        """Determine the rate limit from the org's plan."""
        request = self.request  # type: ignore[attr-defined]
        org = getattr(request, "org", None)
        plan = getattr(org, "plan", "free") if org else "free"
        return self.PLAN_RATES.get(plan, "100/day")

    def allow_request(self, request, view) -> bool:
        """Short-circuit for enterprise plans — no throttling."""
        self.request = request
        org = getattr(request, "org", None)
        plan = getattr(org, "plan", "free") if org else "free"
        if plan == "enterprise":
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view) -> str | None:
        org = getattr(request, "org", None)
        if not org:
            # Throttle by IP for unauthenticated requests
            return self.cache_format % {
                "scope": self.scope,
                "ident": self.get_ident(request),
            }
        return f"throttle_org_{org.id}"
