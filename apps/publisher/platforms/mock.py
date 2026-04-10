import logging
import uuid

from apps.publisher.base import BasePublisher, ErrorCode, PublishResult

logger = logging.getLogger(__name__)


class MockPublisher(BasePublisher):

    platform = "mock"

    def __init__(self, simulate_failure: str | None = None) -> None:
        self.simulate_failure = simulate_failure

    def publish(self, post_target) -> PublishResult:
        self._log_attempt(str(post_target.pk))

        if self.simulate_failure:
            return self._do_failure(post_target)
        return self._do_success(post_target)

    def _do_success(self, post_target) -> PublishResult:
        remote_id = f"mock_{uuid.uuid4().hex[:12]}"

        logger.info(
            "[MockPublisher] Published successfully.",
            extra={
                "post_target_id": str(post_target.pk),
                "platform": self.platform,
                "remote_id": remote_id,
            },
        )

        self._log_success(str(post_target.pk), remote_id)
        return PublishResult.success(
            remote_id=remote_id,
            message=f"[Mock] Post published. Simulated remote ID: {remote_id}",
        )

    def _do_failure(self, post_target) -> PublishResult:
        message = _FAILURE_MESSAGES.get(
            self.simulate_failure,
            f"[Mock] Simulated failure: {self.simulate_failure}",
        )

        logger.warning(
            "[MockPublisher] Simulated failure.",
            extra={
                "post_target_id": str(post_target.pk),
                "platform": self.platform,
                "error_code": self.simulate_failure,
                "error_msg": message,
            },
        )

        self._log_failure(str(post_target.pk), self.simulate_failure, message)
        return PublishResult.failure(error_code=self.simulate_failure, message=message)


# Human-readable messages for each simulated failure

_FAILURE_MESSAGES: dict[str, str] = {
    ErrorCode.AUTH_EXPIRED:        "[Mock] OAuth token has expired. Re-authentication required.",
    ErrorCode.AUTH_REVOKED:        "[Mock] User revoked app access.",
    ErrorCode.AUTH_INSUFFICIENT:   "[Mock] Missing required OAuth scope.",
    ErrorCode.RATE_LIMITED:        "[Mock] Platform rate limit hit. Retry after 60 seconds.",
    ErrorCode.DAILY_LIMIT:         "[Mock] Daily post quota exceeded.",
    ErrorCode.CONTENT_TOO_LONG:    "[Mock] Post content exceeds the platform character limit.",
    ErrorCode.CONTENT_INVALID:     "[Mock] Post content rejected by platform policy.",
    ErrorCode.MEDIA_UPLOAD_FAILED: "[Mock] Media upload failed.",
    ErrorCode.PLATFORM_DOWN:       "[Mock] Platform returned 503. Try again later.",
    ErrorCode.TIMEOUT:             "[Mock] Request timed out.",
    ErrorCode.UNKNOWN:             "[Mock] Unknown error occurred.",
}
