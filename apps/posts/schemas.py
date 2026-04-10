from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PostTargetErrorPayload(BaseModel):

    code: str = Field(description="Machine-readable error code, e.g. 'RATE.LIMITED'.")
    message: str = Field(description="Human-readable failure description.")
    at: datetime = Field(description="UTC datetime when the failure was recorded.")
