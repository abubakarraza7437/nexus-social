from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PublishResult(BaseModel):

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


class PublishSuccessPayload(BaseModel):

    remote_post_id: str = Field(
        description="Platform-assigned post ID returned by the API.",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Platform-specific metadata (e.g. permalink, media IDs).",
    )


class PublishErrorPayload(BaseModel):

    code: str = Field(description="Machine-readable error code from ErrorCode.")
    message: str = Field(description="Human-readable failure description.")
    traceback: str = Field(default="", description="Python traceback string, if available.")
    at: datetime = Field(description="UTC datetime when the failure was recorded.")
