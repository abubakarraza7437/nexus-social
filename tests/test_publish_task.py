import uuid
from contextlib import contextmanager, ExitStack
from unittest.mock import MagicMock, patch

import pytest

from apps.posts.models import PostTarget
from apps.publisher.base import ErrorCode, PublishResult
from apps.publisher.models import PublishJob
from apps.publisher.tasks import RetryablePublishError, publish_post


@contextmanager
def _noop(*_args, **_kwargs):
    """No-op context manager — replaces schema_context and transaction.atomic."""
    yield


def _mock_self(retries=0, task_id="task-abc"):
    """Minimal stand-in for the Celery bound-task self argument."""
    m = MagicMock()
    m.request.retries = retries
    m.request.id = task_id
    m.max_retries = publish_post.max_retries  # 5
    return m


def _make_target(status=PostTarget.Status.SCHEDULED):
    t = MagicMock()
    t.pk = uuid.uuid4()
    t.status = status
    t.post.organization_id = uuid.uuid4()
    return t


def _make_job(retries=0):
    j = MagicMock(spec=PublishJob)
    j.attempt_number = retries + 1
    j.max_attempts = publish_post.max_retries + 1  # 6
    return j


def _run(task_self, target, pub_result, job=None):
    if job is None:
        job = _make_job(task_self.request.retries)

    mock_pub_cls = MagicMock()
    mock_pub_cls.return_value.publish.return_value = pub_result

    pt_mock = MagicMock()
    pt_mock.Status = PostTarget.Status  # preserve real Status enum
    pt_mock.DoesNotExist = PostTarget.DoesNotExist  # preserve real exception class
    pt_mock.objects.select_related.return_value.get.return_value = target

    job_cls_mock = MagicMock()
    job_cls_mock.objects.create.return_value = job

    patches = [
        patch("apps.publisher.tasks.schema_context", side_effect=_noop),
        patch("apps.publisher.tasks.transaction", MagicMock(atomic=_noop)),
        patch("apps.publisher.tasks.PostTarget", pt_mock),
        patch("apps.publisher.tasks.PublishJob", job_cls_mock),
        patch("apps.publisher.tasks.MockPublisher", mock_pub_cls),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        publish_post._orig_run.__func__(task_self, str(target.pk), "public")

    return job


def _run_raises(task_self, target, pub_result, exc_type, job=None):
    """Like _run but expects *exc_type* to be raised; returns (job, exc)."""
    if job is None:
        job = _make_job(task_self.request.retries)

    mock_pub_cls = MagicMock()
    mock_pub_cls.return_value.publish.return_value = pub_result

    pt_mock = MagicMock()
    pt_mock.Status = PostTarget.Status
    pt_mock.DoesNotExist = PostTarget.DoesNotExist
    pt_mock.objects.select_related.return_value.get.return_value = target

    job_cls_mock = MagicMock()
    job_cls_mock.objects.create.return_value = job

    patches = [
        patch("apps.publisher.tasks.schema_context", side_effect=_noop),
        patch("apps.publisher.tasks.transaction", MagicMock(atomic=_noop)),
        patch("apps.publisher.tasks.PostTarget", pt_mock),
        patch("apps.publisher.tasks.PublishJob", job_cls_mock),
        patch("apps.publisher.tasks.MockPublisher", mock_pub_cls),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with pytest.raises(exc_type) as exc_info:
            publish_post._orig_run.__func__(task_self, str(target.pk), "public")

    return job, exc_info


class TestPublishTaskSuccess:

    def test_calls_publisher(self):
        target = _make_target()
        mock_pub_cls = MagicMock()
        mock_pub_cls.return_value.publish.return_value = PublishResult.success(remote_id="t1")

        pt_mock = MagicMock()
        pt_mock.Status = PostTarget.Status
        pt_mock.DoesNotExist = PostTarget.DoesNotExist
        pt_mock.objects.select_related.return_value.get.return_value = target

        job = _make_job()
        job_cls_mock = MagicMock()
        job_cls_mock.objects.create.return_value = job

        with ExitStack() as stack:
            stack.enter_context(patch("apps.publisher.tasks.schema_context", side_effect=_noop))
            stack.enter_context(patch("apps.publisher.tasks.transaction", MagicMock(atomic=_noop)))
            stack.enter_context(patch("apps.publisher.tasks.PostTarget", pt_mock))
            stack.enter_context(patch("apps.publisher.tasks.PublishJob", job_cls_mock))
            stack.enter_context(patch("apps.publisher.tasks.MockPublisher", mock_pub_cls))
            publish_post._orig_run.__func__(_mock_self(), str(target.pk), "public")

        mock_pub_cls.return_value.publish.assert_called_once_with(target)

    def test_calls_mark_success(self):
        target = _make_target()
        job = _run(_mock_self(), target, PublishResult.success(remote_id="t1"))
        job.mark_success.assert_called_once()

    def test_does_not_call_mark_failed(self):
        target = _make_target()
        job = _run(_mock_self(), target, PublishResult.success(remote_id="t1"))
        job.mark_failed.assert_not_called()

    def test_does_not_raise(self):
        target = _make_target()
        _run(_mock_self(), target, PublishResult.success(remote_id="t1"))

    def test_job_created_with_attempt_1_on_first_try(self):
        target = _make_target()
        job = _make_job(retries=0)
        _run(_mock_self(retries=0), target, PublishResult.success(remote_id="t1"), job=job)
        assert job.attempt_number == 1

    def test_job_created_with_max_attempts_6(self):
        target = _make_target()
        job = _make_job(retries=0)
        _run(_mock_self(retries=0), target, PublishResult.success(remote_id="t1"), job=job)
        assert job.max_attempts == 6  # max_retries=5 → 6 total attempts

    def test_celery_task_id_suffixed_with_retry_count(self):
        """Each attempt appends the retry count so IDs are unique across retries."""
        target = _make_target()
        job_cls_mock = MagicMock()
        job_cls_mock.objects.create.return_value = _make_job()

        pt_mock = MagicMock()
        pt_mock.Status = PostTarget.Status
        pt_mock.DoesNotExist = PostTarget.DoesNotExist
        pt_mock.objects.select_related.return_value.get.return_value = target

        mock_pub_cls = MagicMock()
        mock_pub_cls.return_value.publish.return_value = PublishResult.success(remote_id="t1")

        with ExitStack() as stack:
            stack.enter_context(patch("apps.publisher.tasks.schema_context", side_effect=_noop))
            stack.enter_context(patch("apps.publisher.tasks.transaction", MagicMock(atomic=_noop)))
            stack.enter_context(patch("apps.publisher.tasks.PostTarget", pt_mock))
            stack.enter_context(patch("apps.publisher.tasks.PublishJob", job_cls_mock))
            stack.enter_context(patch("apps.publisher.tasks.MockPublisher", mock_pub_cls))
            publish_post._orig_run.__func__(_mock_self(retries=2, task_id="base-id"), str(target.pk), "public")

        _, kwargs = job_cls_mock.objects.create.call_args
        assert kwargs["celery_task_id"] == "base-id-2"


class TestPublishTaskRetry:

    def test_raises_retryable_error_on_non_final_failure(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.RATE_LIMITED, "Rate limited")
        _run_raises(_mock_self(retries=0), target, result, RetryablePublishError)

    def test_calls_mark_failed_before_raising(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.RATE_LIMITED, "Rate limited")
        job, _ = _run_raises(_mock_self(retries=0), target, result, RetryablePublishError)
        job.mark_failed.assert_called_once()

    def test_mark_failed_called_with_schedule_retry_true(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.PLATFORM_DOWN, "Down")
        job, _ = _run_raises(_mock_self(retries=0), target, result, RetryablePublishError)
        _, kwargs = job.mark_failed.call_args
        assert kwargs["schedule_retry"] is True

    def test_does_not_mark_success_on_failure(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.RATE_LIMITED, "Rate limited")
        job, _ = _run_raises(_mock_self(retries=0), target, result, RetryablePublishError)
        job.mark_success.assert_not_called()

    def test_attempt_number_increments_with_retries(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.PLATFORM_DOWN, "Down")
        job = _make_job(retries=3)  # 4th attempt
        _run_raises(_mock_self(retries=3), target, result, RetryablePublishError, job=job)
        assert job.attempt_number == 4

    def test_all_non_final_attempts_raise(self):
        """Attempts 1–5 (retries 0–4) must all raise RetryablePublishError."""
        result = PublishResult.failure(ErrorCode.PLATFORM_DOWN, "Down")
        for retries in range(publish_post.max_retries):  # 0, 1, 2, 3, 4
            target = _make_target()
            _run_raises(_mock_self(retries=retries), target, result, RetryablePublishError)


class TestPublishTaskFinalFailure:

    def test_does_not_raise_on_final_attempt(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.PLATFORM_DOWN, "Still down")
        _run(_mock_self(retries=5), target, result)  # must not raise

    def test_mark_failed_called_with_schedule_retry_false(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.PLATFORM_DOWN, "Still down")
        job = _run(_mock_self(retries=5), target, result)
        _, kwargs = job.mark_failed.call_args
        assert kwargs["schedule_retry"] is False

    def test_error_code_forwarded_to_mark_failed(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.AUTH_EXPIRED, "Token gone")
        job = _run(_mock_self(retries=5), target, result)
        _, kwargs = job.mark_failed.call_args
        assert kwargs["code"] == ErrorCode.AUTH_EXPIRED

    def test_attempt_number_is_6_on_final_attempt(self):
        target = _make_target()
        result = PublishResult.failure(ErrorCode.PLATFORM_DOWN, "Still down")
        job = _make_job(retries=5)
        _run(_mock_self(retries=5), target, result, job=job)
        assert job.attempt_number == 6


class TestPublishTaskGuards:

    def test_skips_already_published_target(self):
        target = _make_target(status=PostTarget.Status.PUBLISHED)
        job_cls_mock = MagicMock()

        pt_mock = MagicMock()
        pt_mock.Status = PostTarget.Status
        pt_mock.DoesNotExist = PostTarget.DoesNotExist
        pt_mock.objects.select_related.return_value.get.return_value = target

        with ExitStack() as stack:
            stack.enter_context(patch("apps.publisher.tasks.schema_context", side_effect=_noop))
            stack.enter_context(patch("apps.publisher.tasks.transaction", MagicMock(atomic=_noop)))
            stack.enter_context(patch("apps.publisher.tasks.PostTarget", pt_mock))
            stack.enter_context(patch("apps.publisher.tasks.PublishJob", job_cls_mock))
            stack.enter_context(patch("apps.publisher.tasks.MockPublisher", MagicMock()))
            publish_post._orig_run.__func__(_mock_self(), str(target.pk), "public")

        job_cls_mock.objects.create.assert_not_called()

    def test_missing_post_target_returns_without_creating_job(self):
        job_cls_mock = MagicMock()

        pt_mock = MagicMock()
        pt_mock.Status = PostTarget.Status
        pt_mock.DoesNotExist = PostTarget.DoesNotExist
        pt_mock.objects.select_related.return_value.get.side_effect = PostTarget.DoesNotExist

        fake_id = str(uuid.uuid4())
        with ExitStack() as stack:
            stack.enter_context(patch("apps.publisher.tasks.schema_context", side_effect=_noop))
            stack.enter_context(patch("apps.publisher.tasks.transaction", MagicMock(atomic=_noop)))
            stack.enter_context(patch("apps.publisher.tasks.PostTarget", pt_mock))
            stack.enter_context(patch("apps.publisher.tasks.PublishJob", job_cls_mock))
            stack.enter_context(patch("apps.publisher.tasks.MockPublisher", MagicMock()))
            publish_post._orig_run.__func__(_mock_self(), fake_id, "public")  # must not raise

        job_cls_mock.objects.create.assert_not_called()

    def test_active_job_lock_returns_early(self):
        """IntegrityError from DB constraint causes the task to return early."""
        from django.db import IntegrityError

        target = _make_target()
        job_cls_mock = MagicMock()
        job_cls_mock.objects.create.side_effect = IntegrityError

        pt_mock = MagicMock()
        pt_mock.Status = PostTarget.Status
        pt_mock.DoesNotExist = PostTarget.DoesNotExist
        pt_mock.objects.select_related.return_value.get.return_value = target

        mock_pub_cls = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch("apps.publisher.tasks.schema_context", side_effect=_noop))
            stack.enter_context(patch("apps.publisher.tasks.transaction", MagicMock(atomic=_noop)))
            stack.enter_context(patch("apps.publisher.tasks.PostTarget", pt_mock))
            stack.enter_context(patch("apps.publisher.tasks.PublishJob", job_cls_mock))
            stack.enter_context(patch("apps.publisher.tasks.MockPublisher", mock_pub_cls))
            publish_post._orig_run.__func__(_mock_self(), str(target.pk), "public")  # must not raise

        mock_pub_cls.return_value.publish.assert_not_called()


# --------------------------------------------------------------------------- #
# on_failure handler                                                           #
# --------------------------------------------------------------------------- #

def _call_on_failure(exc, post_target_id=None, schema_name="public", job=None):
    """
    Invoke publish_post.on_failure with all DB calls mocked.

    Returns the job mock so callers can assert on mark_failed calls.
    """
    if post_target_id is None:
        post_target_id = str(uuid.uuid4())

    job_cls_mock = MagicMock()
    if job is not None:
        job_cls_mock.objects.filter.return_value.first.return_value = job
    else:
        job_cls_mock.objects.filter.return_value.first.return_value = None

    with ExitStack() as stack:
        stack.enter_context(patch("apps.publisher.tasks.schema_context", side_effect=_noop))
        stack.enter_context(patch("apps.publisher.tasks.PublishJob", job_cls_mock))
        publish_post.on_failure(
            exc=exc,
            task_id="task-xyz",
            args=[post_target_id, schema_name],
            kwargs={},
            einfo=None,
        )

    return job_cls_mock


class TestOnFailureHandler:

    def test_marks_running_job_failed(self):
        job = MagicMock()
        _call_on_failure(RuntimeError("boom"), job=job)
        job.mark_failed.assert_called_once()

    def test_mark_failed_called_with_schedule_retry_false(self):
        job = MagicMock()
        _call_on_failure(RuntimeError("boom"), job=job)
        _, kwargs = job.mark_failed.call_args
        assert kwargs["schedule_retry"] is False

    def test_failure_message_stored(self):
        job = MagicMock()
        _call_on_failure(RuntimeError("disk full"), job=job)
        _, kwargs = job.mark_failed.call_args
        assert "disk full" in kwargs["message"]

    def test_error_code_is_unknown(self):
        job = MagicMock()
        _call_on_failure(ValueError("unexpected"), job=job)
        _, kwargs = job.mark_failed.call_args
        assert kwargs["code"] == ErrorCode.UNKNOWN

    def test_no_running_job_is_a_noop(self):
        """If the job was never created (crash before step 3), handler must not raise."""
        job_cls_mock = _call_on_failure(RuntimeError("early crash"), job=None)
        # filter().first() returned None — no mark_failed call on anything
        assert job_cls_mock.objects.filter.return_value.first.return_value is None

    def test_short_args_is_a_noop(self):
        """Missing args (edge case) must not raise."""
        with patch("apps.publisher.tasks.schema_context", side_effect=_noop):
            publish_post.on_failure(
                exc=RuntimeError("boom"),
                task_id="t",
                args=[],       # no post_target_id / schema_name
                kwargs={},
                einfo=None,
            )

    def test_filters_only_running_jobs(self):
        """Handler must only consider RUNNING jobs, not failed/success ones."""
        job_cls_mock = MagicMock()
        job_cls_mock.Status = PublishJob.Status   # preserve real enum so assertion matches
        job_cls_mock.objects.filter.return_value.first.return_value = None
        target_id = str(uuid.uuid4())

        with ExitStack() as stack:
            stack.enter_context(patch("apps.publisher.tasks.schema_context", side_effect=_noop))
            stack.enter_context(patch("apps.publisher.tasks.PublishJob", job_cls_mock))
            publish_post.on_failure(
                exc=RuntimeError("x"),
                task_id="t",
                args=[target_id, "public"],
                kwargs={},
                einfo=None,
            )

        job_cls_mock.objects.filter.assert_called_once_with(
            target_id=target_id,
            status=PublishJob.Status.RUNNING,
        )

    def test_db_error_in_handler_does_not_propagate(self):
        """If the DB call inside on_failure itself raises, it must be swallowed."""
        with ExitStack() as stack:
            stack.enter_context(
                patch("apps.publisher.tasks.schema_context", side_effect=Exception("db down"))
            )
            publish_post.on_failure(
                exc=RuntimeError("original error"),
                task_id="t",
                args=[str(uuid.uuid4()), "public"],
                kwargs={},
                einfo=None,
            )  # must not raise
