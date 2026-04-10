"""
Tests — apps.publisher.platforms.mock
"""

import logging

import pytest

from apps.publisher.base import ErrorCode, PublishResult
from apps.publisher.platforms.mock import MockPublisher


class StubPostTarget:
    def __init__(self, pk="target-abc"):
        self.pk = pk


# --------------------------------------------------------------------------- #
# Success                                                                      #
# --------------------------------------------------------------------------- #

class TestMockPublisherSuccess:
    def test_returns_ok_true(self):
        result = MockPublisher().publish(StubPostTarget())
        assert result.ok is True

    def test_returns_publish_result(self):
        result = MockPublisher().publish(StubPostTarget())
        assert isinstance(result, PublishResult)

    def test_remote_id_is_populated(self):
        result = MockPublisher().publish(StubPostTarget())
        assert result.remote_id.startswith("mock_")
        assert len(result.remote_id) > 5

    def test_remote_id_is_unique_per_call(self):
        target = StubPostTarget()
        r1 = MockPublisher().publish(target)
        r2 = MockPublisher().publish(target)
        assert r1.remote_id != r2.remote_id

    def test_no_error_code_on_success(self):
        result = MockPublisher().publish(StubPostTarget())
        assert result.error_code == ""

    def test_logs_success(self, caplog):
        import logging as _logging
        apps_logger = _logging.getLogger("apps")
        apps_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="apps.publisher.platforms.mock"):
                MockPublisher().publish(StubPostTarget())
            assert "Published successfully" in caplog.text
        finally:
            apps_logger.propagate = False


# --------------------------------------------------------------------------- #
# Simulated failures                                                           #
# --------------------------------------------------------------------------- #

class TestMockPublisherFailure:
    def test_simulate_failure_returns_ok_false(self):
        result = MockPublisher(simulate_failure=ErrorCode.RATE_LIMITED).publish(StubPostTarget())
        assert result.ok is False

    def test_simulate_failure_sets_error_code(self):
        result = MockPublisher(simulate_failure=ErrorCode.AUTH_EXPIRED).publish(StubPostTarget())
        assert result.error_code == ErrorCode.AUTH_EXPIRED

    def test_simulate_failure_remote_id_is_empty(self):
        result = MockPublisher(simulate_failure=ErrorCode.PLATFORM_DOWN).publish(StubPostTarget())
        assert result.remote_id == ""

    def test_simulate_failure_has_message(self):
        result = MockPublisher(simulate_failure=ErrorCode.RATE_LIMITED).publish(StubPostTarget())
        assert result.message != ""

    def test_logs_warning_on_failure(self, caplog):
        import logging as _logging
        apps_logger = _logging.getLogger("apps")
        apps_logger.propagate = True
        try:
            with caplog.at_level(logging.WARNING, logger="apps.publisher.platforms.mock"):
                MockPublisher(simulate_failure=ErrorCode.TIMEOUT).publish(StubPostTarget())
            assert "Simulated failure" in caplog.text
        finally:
            apps_logger.propagate = False

    @pytest.mark.parametrize("error_code", [
        ErrorCode.AUTH_EXPIRED,
        ErrorCode.AUTH_REVOKED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.DAILY_LIMIT,
        ErrorCode.CONTENT_TOO_LONG,
        ErrorCode.CONTENT_INVALID,
        ErrorCode.MEDIA_UPLOAD_FAILED,
        ErrorCode.PLATFORM_DOWN,
        ErrorCode.TIMEOUT,
        ErrorCode.UNKNOWN,
    ])
    def test_all_error_codes_produce_failure(self, error_code):
        result = MockPublisher(simulate_failure=error_code).publish(StubPostTarget())
        assert result.ok is False
        assert result.error_code == error_code
        assert result.message != ""

    def test_unknown_error_code_still_returns_failure(self):
        result = MockPublisher(simulate_failure="CUSTOM.ERROR").publish(StubPostTarget())
        assert result.ok is False
        assert result.error_code == "CUSTOM.ERROR"
        assert "CUSTOM.ERROR" in result.message
