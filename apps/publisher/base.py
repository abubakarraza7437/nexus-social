"""
Publisher · Base interface
==========================
All platform publishers must subclass BasePublisher and implement publish().

Usage (in Celery task)
----------------------
    from apps.publisher.platforms.facebook import FacebookPublisher

    publisher = FacebookPublisher(account=social_account)
    result = publisher.publish(post_target)

    if result.ok:
        job.mark_success({"remote_post_id": result.remote_id})
    else:
        job.mark_failed(code=result.error_code, message=result.message)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Response                                                                     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PublishResult:
    """
    Standardised return value from every publisher.

    Attributes:
        ok:           True on success, False on any failure.
        remote_id:    Platform-assigned post ID (e.g. tweet ID, FB post ID).
                      Empty string on failure.
        message:      Human-readable description of what happened.
        error_code:   Machine-readable failure code for retry/alerting logic.
                      Empty string on success.
        extra:        Any additional platform-specific metadata
                      (e.g. permalink, media IDs). Never relied on by core logic.
    """

    ok: bool
    remote_id: str = ""
    message: str = ""
    error_code: str = ""
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Named constructors — prefer these over direct instantiation         #
    # ------------------------------------------------------------------ #

    @classmethod
    def success(cls, remote_id: str, message: str = "Published.", **extra) -> PublishResult:
        return cls(ok=True, remote_id=remote_id, message=message, extra=extra)

    @classmethod
    def failure(cls, error_code: str, message: str, **extra) -> PublishResult:
        return cls(ok=False, error_code=error_code, message=message, extra=extra)


# --------------------------------------------------------------------------- #
# Standard error codes                                                         #
# --------------------------------------------------------------------------- #

class ErrorCode:
    """
    Shared error codes across all platform publishers.

    Keep codes uppercase and dot-namespaced so they sort cleanly in logs.
    Platform-specific codes should be prefixed with the platform name,
    e.g. "TWITTER.DUPLICATE_CONTENT".
    """

    # Auth
    AUTH_EXPIRED = "AUTH.EXPIRED"  # OAuth token expired
    AUTH_REVOKED = "AUTH.REVOKED"  # User revoked app access
    AUTH_INSUFFICIENT = "AUTH.INSUFFICIENT"  # Missing required scope

    # Rate limits
    RATE_LIMITED = "RATE.LIMITED"  # Platform rate limit hit
    DAILY_LIMIT = "RATE.DAILY_LIMIT"  # Daily post quota exceeded

    # Content
    CONTENT_TOO_LONG = "CONTENT.TOO_LONG"
    CONTENT_INVALID = "CONTENT.INVALID"  # Rejected by platform (policy, format)
    MEDIA_UPLOAD_FAILED = "MEDIA.UPLOAD_FAILED"

    # Infrastructure
    PLATFORM_DOWN = "PLATFORM.DOWN"  # 5xx from platform API
    TIMEOUT = "NETWORK.TIMEOUT"
    UNKNOWN = "UNKNOWN"


# --------------------------------------------------------------------------- #
# Abstract base                                                                #
# --------------------------------------------------------------------------- #

class BasePublisher(ABC):
    """
    Contract every platform publisher must satisfy.

    Subclasses
    ----------
    Implement publish() only. Do not override __init__ signature without
    calling super().__init__().

    Thread safety
    -------------
    Publisher instances are created per-task invocation inside Celery workers.
    Do not share state across calls.
    """

    #: Human-readable platform name — must be set on every concrete subclass.
    platform: str = ""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "__abstractmethods__", None) and not cls.platform:
            raise TypeError(
                f"{cls.__name__} must set a non-empty class attribute 'platform'."
            )

    @abstractmethod
    def publish(self, post_target) -> PublishResult:
        """
        Deliver the content described by *post_target* to the platform.

        Contract
        --------
        - MUST return a PublishResult — never raise unhandled exceptions.
        - MUST be idempotent: calling publish() twice with the same
          post_target must not create duplicate posts. Check for an
          existing remote_id on post_target before calling the API.
        - MUST NOT mutate post_target or PublishJob — that is the
          Celery task's responsibility after inspecting the result.

        Args:
            post_target: apps.posts.models.PostTarget instance describing
                         the platform, account, and content to publish.

        Returns:
            PublishResult with ok=True on success, ok=False on any failure.
        """

    # ------------------------------------------------------------------ #
    # Helpers available to all subclasses                                 #
    # ------------------------------------------------------------------ #

    def _log_attempt(self, post_target_id: str) -> None:
        logger.info(
            "publisher.attempt",
            extra={"platform": self.platform, "post_target_id": post_target_id},
        )

    def _log_success(self, post_target_id: str, remote_id: str) -> None:
        logger.info(
            "publisher.success",
            extra={
                "platform": self.platform,
                "post_target_id": post_target_id,
                "remote_id": remote_id,
            },
        )

    def _log_failure(self, post_target_id: str, error_code: str, message: str) -> None:
        logger.warning(
            "publisher.failure",
            extra={
                "platform": self.platform,
                "post_target_id": post_target_id,
                "error_code": error_code,
                "message": message,
            },
        )
