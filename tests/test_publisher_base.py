"""
Tests — apps.publisher.base
============================
Tests for PublishResult, ErrorCode, and BasePublisher contract enforcement.
Uses a lightweight stub publisher — no real platform calls.
"""

import pytest
from apps.publisher.base import BasePublisher, ErrorCode, PublishResult


# --------------------------------------------------------------------------- #
# Stub implementations                                                         #
# --------------------------------------------------------------------------- #

class StubPublisher(BasePublisher):
    """Minimal concrete publisher used across all tests."""
    platform = "stub"

    def __init__(self, result: PublishResult):
        self._result = result

    def publish(self, post_target) -> PublishResult:
        return self._result


class StubPostTarget:
    """Minimal stand-in for apps.posts.models.PostTarget."""
    def __init__(self, pk="target-123", remote_post_id=""):
        self.pk = pk
        self.remote_post_id = remote_post_id


# --------------------------------------------------------------------------- #
# PublishResult                                                                #
# --------------------------------------------------------------------------- #

class TestPublishResult:
    def test_success_sets_ok_true(self):
        result = PublishResult.success(remote_id="abc123")
        assert result.ok is True
        assert result.remote_id == "abc123"
        assert result.error_code == ""

    def test_success_default_message(self):
        result = PublishResult.success(remote_id="x")
        assert result.message == "Published."

    def test_success_custom_message(self):
        result = PublishResult.success(remote_id="x", message="Tweet posted.")
        assert result.message == "Tweet posted."

    def test_success_extra_kwargs(self):
        result = PublishResult.success(remote_id="x", permalink="https://t.co/x")
        assert result.extra == {"permalink": "https://t.co/x"}

    def test_failure_sets_ok_false(self):
        result = PublishResult.failure(ErrorCode.RATE_LIMITED, "Too many requests")
        assert result.ok is False
        assert result.error_code == ErrorCode.RATE_LIMITED
        assert result.remote_id == ""

    def test_failure_message(self):
        result = PublishResult.failure(ErrorCode.AUTH_EXPIRED, "Token expired")
        assert result.message == "Token expired"

    def test_failure_extra_kwargs(self):
        result = PublishResult.failure(ErrorCode.UNKNOWN, "err", retry_after=60)
        assert result.extra == {"retry_after": 60}

    def test_is_immutable(self):
        result = PublishResult.success(remote_id="x")
        with pytest.raises(Exception):  # frozen=True raises FrozenInstanceError
            result.ok = False  # type: ignore[misc]

    def test_empty_extra_by_default(self):
        r1 = PublishResult.success(remote_id="a")
        r2 = PublishResult.success(remote_id="b")
        # Each instance must have its own dict — not a shared default
        assert r1.extra is not r2.extra


# --------------------------------------------------------------------------- #
# ErrorCode                                                                    #
# --------------------------------------------------------------------------- #

class TestErrorCode:
    def test_auth_codes_exist(self):
        assert ErrorCode.AUTH_EXPIRED
        assert ErrorCode.AUTH_REVOKED
        assert ErrorCode.AUTH_INSUFFICIENT

    def test_rate_codes_exist(self):
        assert ErrorCode.RATE_LIMITED
        assert ErrorCode.DAILY_LIMIT

    def test_content_codes_exist(self):
        assert ErrorCode.CONTENT_TOO_LONG
        assert ErrorCode.CONTENT_INVALID
        assert ErrorCode.MEDIA_UPLOAD_FAILED

    def test_infra_codes_exist(self):
        assert ErrorCode.PLATFORM_DOWN
        assert ErrorCode.TIMEOUT
        assert ErrorCode.UNKNOWN

    def test_subclass_can_add_platform_codes(self):
        class TwitterErrorCode(ErrorCode):
            DUPLICATE = "TWITTER.DUPLICATE_CONTENT"

        assert TwitterErrorCode.DUPLICATE == "TWITTER.DUPLICATE_CONTENT"
        assert TwitterErrorCode.RATE_LIMITED == ErrorCode.RATE_LIMITED


# --------------------------------------------------------------------------- #
# BasePublisher — contract enforcement                                         #
# --------------------------------------------------------------------------- #

class TestBasePublisherContract:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            BasePublisher()  # type: ignore[abstract]

    def test_subclass_without_publish_cannot_be_instantiated(self):
        class Incomplete(BasePublisher):
            platform = "incomplete"
            # publish() not implemented

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_without_platform_raises_on_definition(self):
        with pytest.raises(TypeError, match="platform"):
            class NoPlatform(BasePublisher):
                # platform not set
                def publish(self, post_target) -> PublishResult:
                    return PublishResult.success(remote_id="x")

    def test_concrete_subclass_instantiates(self):
        publisher = StubPublisher(result=PublishResult.success(remote_id="x"))
        assert publisher.platform == "stub"

    def test_publish_returns_publish_result(self):
        expected = PublishResult.success(remote_id="tweet_99")
        publisher = StubPublisher(result=expected)
        result = publisher.publish(StubPostTarget())
        assert isinstance(result, PublishResult)
        assert result is expected


# --------------------------------------------------------------------------- #
# BasePublisher — success / failure paths                                      #
# --------------------------------------------------------------------------- #

class TestBasePublisherPaths:
    def test_successful_publish(self):
        result = PublishResult.success(remote_id="fb_post_42", message="Posted to Facebook.")
        publisher = StubPublisher(result=result)

        outcome = publisher.publish(StubPostTarget())

        assert outcome.ok is True
        assert outcome.remote_id == "fb_post_42"
        assert outcome.error_code == ""

    def test_failed_publish_rate_limit(self):
        result = PublishResult.failure(ErrorCode.RATE_LIMITED, "Rate limit hit, retry in 60s")
        publisher = StubPublisher(result=result)

        outcome = publisher.publish(StubPostTarget())

        assert outcome.ok is False
        assert outcome.error_code == ErrorCode.RATE_LIMITED
        assert "retry" in outcome.message

    def test_failed_publish_auth_expired(self):
        result = PublishResult.failure(ErrorCode.AUTH_EXPIRED, "OAuth token has expired")
        publisher = StubPublisher(result=result)

        outcome = publisher.publish(StubPostTarget())

        assert outcome.ok is False
        assert outcome.error_code == ErrorCode.AUTH_EXPIRED

    def test_failed_publish_platform_down(self):
        result = PublishResult.failure(ErrorCode.PLATFORM_DOWN, "503 from API")
        publisher = StubPublisher(result=result)

        outcome = publisher.publish(StubPostTarget())

        assert outcome.ok is False
        assert outcome.error_code == ErrorCode.PLATFORM_DOWN

    def test_publish_job_integration_pattern(self):
        """
        Mirrors how the Celery task will use the publisher:
            result = publisher.publish(post_target)
            if result.ok:
                job.mark_success({"remote_post_id": result.remote_id})
            else:
                job.mark_failed(code=result.error_code, message=result.message)
        """
        success_result = PublishResult.success(remote_id="ig_123")
        publisher = StubPublisher(result=success_result)

        result = publisher.publish(StubPostTarget())

        # Simulate what the Celery task does with the result
        if result.ok:
            job_payload = {"remote_post_id": result.remote_id}
        else:
            job_payload = {"code": result.error_code, "message": result.message}

        assert job_payload == {"remote_post_id": "ig_123"}
