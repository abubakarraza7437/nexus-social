"""
Publisher · Pydantic schemas
============================
Typed, validated structures for publisher inputs and outputs.

  PublishResult       — returned by every BasePublisher.publish() call
  PublishSuccessPayload — stored in PublishJob.result (JSONField)
  PublishErrorPayload   — stored in PublishJob.error  (JSONField)

Storing via model_dump(mode="json") ensures datetimes are ISO strings
and the shape written to the DB is always validated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# PublishResult — returned by publishers                                       #
# --------------------------------------------------------------------------- #

class PublishResult(BaseModel):
    """
    Standardised return value from every BasePublisher.publish() call.

    Immutable (frozen). Use the named constructors instead of instantiating
    directly:

        return PublishResult.success(remote_id="tweet_123")
        return PublishResult.failure(ErrorCode.RATE_LIMITED, "Too many requests")
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    remote_id: str = ""
    message: str = ""
    error_code: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success(
        cls,
        remote_id: str,
        message: str = "Published.",
        **extra: Any,
    ) -> PublishResult:
        return cls(ok=True, remote_id=remote_id, message=message, extra=extra)

    @classmethod
    def failure(
        cls,
        error_code: str,
        message: str,
        **extra: Any,
    ) -> PublishResult:
        return cls(ok=False, error_code=error_code, message=message, extra=extra)


# --------------------------------------------------------------------------- #
# PublishSuccessPayload — stored in PublishJob.result JSONField                #
# --------------------------------------------------------------------------- #

class PublishSuccessPayload(BaseModel):
    """
    Validated payload written to PublishJob.result on a successful publish.

    Persist with:
        job.result = payload.model_dump(mode="json")

    Read back with:
        payload = PublishSuccessPayload.model_validate(job.result)
    """

    remote_post_id: str = Field(
        description="Platform-assigned post ID returned by the API.",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Platform-specific metadata (e.g. permalink, media IDs).",
    )


# --------------------------------------------------------------------------- #
# PublishErrorPayload — stored in PublishJob.error JSONField                  #
# --------------------------------------------------------------------------- #

class PublishErrorPayload(BaseModel):
    """
    Validated payload written to PublishJob.error on a failed publish.

    Persist with:
        job.error = payload.model_dump(mode="json")

    Read back with:
        payload = PublishErrorPayload.model_validate(job.error)
    """

    code: str = Field(description="Machine-readable error code from ErrorCode.")
    message: str = Field(description="Human-readable failure description.")
    traceback: str = Field(default="", description="Python traceback string, if available.")
    at: datetime = Field(description="UTC datetime when the failure was recorded.")
