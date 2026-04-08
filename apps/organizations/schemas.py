"""
Organizations · Pydantic schemas
=================================
Typed, validated structure for Organization JSON fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlanLimits(BaseModel):
    """
    Validated snapshot of a subscription plan's feature limits.

    Stored in Organization.plan_limits (JSONField). A value of None means
    the limit is unlimited for that plan tier.

    Persist with:
        org.plan_limits = PlanLimits.model_validate(settings.PLAN_LIMITS[plan]).model_dump(mode="json")

    Read back with:
        limits = PlanLimits.model_validate(org.plan_limits)
    """

    social_accounts: int | None = Field(
        default=None,
        description="Max connected social accounts. None = unlimited.",
    )
    scheduled_posts_per_month: int | None = Field(
        default=None,
        description="Max posts that can be scheduled per calendar month. None = unlimited.",
    )
    team_members: int | None = Field(
        default=None,
        description="Max organisation members. None = unlimited.",
    )
    analytics_history_days: int | None = Field(
        default=None,
        description="How many days of analytics history are accessible. None = unlimited.",
    )
    ai_credits_per_month: int | None = Field(
        default=None,
        description="AI caption/hashtag generation credits per month. None = unlimited.",
    )
    approval_workflows: bool = Field(
        default=False,
        description="Whether multi-step post approval workflows are enabled.",
    )
    unified_inbox: Literal["basic", "full"] | None = Field(
        default=None,
        description="Inbox access level: 'basic', 'full', or None (no inbox).",
    )
    custom_reports: bool = Field(
        default=False,
        description="Whether custom analytics report generation is enabled.",
    )
    api_access: bool = Field(
        default=False,
        description="Whether direct API access is permitted.",
    )
    sso: bool = Field(
        default=False,
        description="Whether Single Sign-On (SSO) is available (enterprise only).",
    )
    sla: str = Field(
        default="",
        description="SLA uptime commitment string, e.g. '99.9%' (enterprise only).",
    )
