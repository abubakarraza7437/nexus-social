from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlanLimits(BaseModel):

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
