"""Step 7: plain failure messages, which failures are retried, retry timing, and the
Celery task re-queuing itself with the retry token."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.core.services.failures import (
    Failure,
    TooManyRunsError,
    explain,
    plan_retry,
    retry_delay_seconds,
    technical_details,
)


def from_library(
    module: str, name: str, wrap: str | None = "ExtractionError"
) -> Exception:
    """An error as a library would raise it (e.g. openai.RateLimitError), optionally
    wrapped the way extraction_agent wraps it."""
    error_class = type(name, (Exception,), {"__module__": module})
    wrapper = type(
        wrap or "Wrapper", (Exception,), {"__module__": "src.control.agents.x"}
    )
    try:
        try:
            raise error_class("provider message")
        except Exception as inner:
            if wrap is None:
                raise
            raise wrapper("The LLM call failed") from inner
    except Exception as exc:  # we want the exception object back
        return exc
    raise AssertionError("unreachable")


# --- what failed, in plain words ------------------------------------------------------


def test_ai_provider_hiccups_are_temporary() -> None:
    for name in (
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
    ):
        failure = explain(from_library("openai", name))
        assert failure.temporary, name
        assert failure.message.startswith("The AI model did not answer")


def test_unusable_ai_answer_is_temporary() -> None:
    assert explain(
        from_library("src.control.agents", "StructuredOutputError", wrap=None)
    ).temporary


def test_wrong_api_key_or_model_is_not_retried() -> None:
    for name in ("AuthenticationError", "PermissionDeniedError", "NotFoundError"):
        failure = explain(from_library("openai", name))
        assert not failure.temporary, name
        assert "API key or model name" in failure.message


def test_database_and_redis_outages_are_temporary() -> None:
    db = explain(from_library("sqlalchemy.exc", "OperationalError", wrap=None))
    assert db.temporary and "database" in db.message
    cache = explain(from_library("redis.exceptions", "ConnectionError", wrap=None))
    assert cache.temporary and "Redis" in cache.message
    assert explain(ConnectionRefusedError("refused")).temporary
    assert explain(TimeoutError()).temporary


def test_a_bug_is_not_retried_and_shows_no_technical_text() -> None:
    failure = explain(KeyError("employee_id"))
    assert not failure.temporary
    assert failure.message == "An unexpected error stopped processing."
    assert "KeyError" not in failure.message + failure.advice


def test_worker_that_keeps_stopping_is_not_retried() -> None:
    failure = explain(TooManyRunsError(4))
    assert not failure.temporary and "stopped 3 times" in failure.message


def test_technical_details_list_the_whole_chain() -> None:
    details = technical_details(from_library("openai", "RateLimitError"))
    assert "ExtractionError: The LLM call failed" in details
    assert "caused by openai.RateLimitError: provider message" in details


# --- when to try again
# ------------------------------------------------------------------


def test_delay_grows_four_times_and_is_capped_at_an_hour() -> None:
    assert [retry_delay_seconds(n, 60) for n in (1, 2, 3, 4)] == [60, 240, 960, 3600]


def test_retry_only_temporary_failures_while_runs_are_left() -> None:
    now = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    temporary = Failure("x", temporary=True, advice="y")
    plan = plan_retry(temporary, 1, max_attempts=3, base_delay=60, now=now)
    assert plan.retry and plan.delay_seconds == 60
    assert plan.retry_at == now + timedelta(seconds=60)
    assert (
        plan_retry(temporary, 2, max_attempts=3, base_delay=60, now=now).delay_seconds
        == 240
    )
    assert not plan_retry(temporary, 3, max_attempts=3, base_delay=60).retry  # last run
    permanent = Failure("x", temporary=False, advice="y")
    assert not plan_retry(permanent, 1, max_attempts=3, base_delay=60).retry


# --- the Celery task
# --------------------------------------------------------------------


def test_task_requeues_itself_with_the_token_and_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.control.workers import tasks
    from src.core.services.processing_service import RetryLater

    token = uuid.uuid4()
    seen: dict[str, Any] = {}

    async def failing(*_: Any, **kwargs: Any) -> None:
        seen.update(kwargs)
        raise RetryLater(token, 240)

    class RequeuedError(Exception):
        pass

    def fake_retry(**kwargs: Any) -> Exception:
        seen["retry"] = kwargs
        return RequeuedError()

    monkeypatch.setattr(tasks, "process_submission_by_id", failing)
    monkeypatch.setattr(tasks.process_submission, "retry", fake_retry)
    submission_id = str(uuid.uuid4())
    with pytest.raises(RequeuedError):
        tasks.process_submission(submission_id, None, None)

    assert seen["retry_token"] is None  # the first run has no token
    assert seen["retry"] == {
        "args": (submission_id, None, str(token)),
        "countdown": 240,
    }
