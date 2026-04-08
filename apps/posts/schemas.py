"""
Posts · Pydantic schemas
========================
Typed, validated structures for PostTarget JSON fields.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PostTargetErrorPayload(BaseModel):
    """
    Stored in PostTarget.error (JSONField) on a failed delivery.

    Persist with:
        target.error = PostTargetErrorPayload(...).model_dump(mode="json")

    Read back with:
        payload = PostTargetErrorPayload.model_validate(target.error)
    """

    code: str = Field(description="Machine-readable error code, e.g. 'RATE.LIMITED'.")
    message: str = Field(description="Human-readable failure description.")
    at: datetime = Field(description="UTC datetime when the failure was recorded.")
