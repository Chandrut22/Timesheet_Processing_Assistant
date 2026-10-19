"""Why processing failed, in words a reviewer understands, and whether trying again
later can help.

explain() looks at the error and the errors it was raised from (__cause__ /
__context__). Libraries are recognised by module and class name, so this file needs
none of them installed (the API never loads the AI libraries)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

AI_MODULES = frozenset(
    {
        "openai",
        "anthropic",
        "groq",
        "google",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langchain_anthropic",
        "langchain_groq",
        "langchain_google_genai",
    }
)
# AI provider errors that trying again will not fix: wrong key, no access, unknown model.
AI_SETUP_ERRORS = frozenset(
    {"AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError"}
)
OUR_AI_ERRORS = frozenset({"ExtractionError", "StructuredOutputError"})
DB_ERRORS = frozenset(
    {
        "OperationalError",
        "InterfaceError",
        "DisconnectionError",
        "TimeoutError",
        "ConnectionDoesNotExistError",
        "CannotConnectNowError",
        "TooManyConnectionsError",
    }
)
REDIS_ERRORS = frozenset({"ConnectionError", "TimeoutError", "BusyLoadingError"})


class TooManyRunsError(Exception):
    """The job was started more times than allowed: the worker kept stopping mid-way
    (crash, out of memory) and the queue handed the job out again each time."""

    def __init__(self, runs: int) -> None:
        super().__init__(f"started {runs} times")
        self.runs = runs


# How providers say "the request is longer than the model's context window". They send it
# as a "bad request", which would otherwise read as "API key or model not accepted".
CONTEXT_LIMIT_MARKERS = (
    "context_length_exceeded",
    "context length",
    "context window",
    "maximum context",
    "too many tokens",
    "prompt is too long",
    "input is too long",
    "reduce the length",
    "request too large",
)


class AnswerTooLongError(Exception):
    """The AI's answer hit the output limit twice: the document holds more than one
    answer can carry (many people or days)."""


class JobTooSlowError(Exception):
    """The job ran longer than WORKER_JOB_TIMEOUT_SECONDS and was stopped."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"stopped after {seconds} s")
        self.seconds = seconds


@dataclass(frozen=True, slots=True)
class Failure:
    message: str  # what happened, for people
    temporary: bool  # True = trying again later can help
    advice: str  # what to do if it keeps failing


def _chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _origin(exc: BaseException) -> tuple[str, str]:
    """(top-level package, class name), e.g. ('openai', 'RateLimitError')."""
    return type(exc).__module__.split(".")[0], type(exc).__name__


def _minutes(seconds: int) -> str:
    minutes = max(round(seconds / 60), 1)
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def explain(exc: BaseException) -> Failure:
    chain = list(_chain(exc))
    origins = [_origin(e) for e in chain]

    if isinstance(exc, TooManyRunsError):
        return Failure(
            f"The worker stopped {exc.runs - 1} times while processing this email "
            "(often a very large or damaged file).",
            temporary=False,
            advice="Check the attachments; remove or replace the problem file, then "
            "reprocess or upload again.",
        )
    if isinstance(exc, JobTooSlowError):
        return Failure(
            f"Processing took longer than {_minutes(exc.seconds)} and was stopped "
            "(usually a very large or slow-to-read file).",
            temporary=False,  # the same file would take as long again
            advice="Split the file or send a smaller / clearer copy, then reprocess.",
        )
    if any(isinstance(e, AnswerTooLongError) for e in chain):
        return Failure(
            "The AI's answer was too long and got cut off: the document holds too many "
            "people or days for one answer.",
            temporary=False,  # the same document would be cut off again
            advice="Split the file (for example one sheet or a few people per file), or an "
            "admin raises LLM_MAX_OUTPUT_TOKENS; then reprocess.",
        )
    if any(marker in str(e).lower() for e in chain for marker in CONTEXT_LIMIT_MARKERS):
        return Failure(
            "The document is too long for the AI model.",
            temporary=False,
            advice="Split the file, or an admin lowers LLM_MAX_INPUT_CHARS (or picks a model "
            "with a larger context window); then reprocess.",
        )
    if any(pkg in AI_MODULES and name in AI_SETUP_ERRORS for pkg, name in origins):
        return Failure(
            "The AI model refused the request: the API key or model name is not accepted.",
            temporary=False,
            advice="An admin must fix the AI settings; then reprocess this email.",
        )
    if any(pkg in AI_MODULES or name in OUR_AI_ERRORS for pkg, name in origins):
        return Failure(
            "The AI model did not answer, or its answer could not be used.",
            temporary=True,
            advice="If it keeps failing, check the AI provider's status, then reprocess.",
        )
    if any(pkg in ("sqlalchemy", "asyncpg") and name in DB_ERRORS for pkg, name in origins):
        return Failure(
            "The database could not be reached.",
            temporary=True,
            advice="Check that the database is running, then reprocess.",
        )
    if any(pkg == "redis" and name in REDIS_ERRORS for pkg, name in origins):
        return Failure(
            "The job queue (Redis) could not be reached.",
            temporary=True,
            advice="Check that Redis is running, then reprocess.",
        )
    if any(isinstance(e, (TimeoutError, ConnectionError)) for e in chain):
        return Failure(
            "A connected service did not answer in time.",
            temporary=True,
            advice="If it keeps failing, check the services are running, then reprocess.",
        )
    return Failure(
        "An unexpected error stopped processing.",
        temporary=False,
        advice="The technical details are in the processing log. Reprocess after the "
        "cause is fixed.",
    )


def technical_details(exc: BaseException, limit: int = 4000) -> str:
    """The error and what caused it, one per line, for the processing log."""
    lines = [f"{type(e).__module__}.{type(e).__name__}: {e}" for e in _chain(exc)]
    return "\n  caused by ".join(lines)[:limit]


# --- retry policy ---------------------------------------------------------------------


def retry_delay_seconds(attempt: int, base: int) -> int:
    """Wait before the next run, after run number `attempt` failed: base, 4x base, ...
    capped at one hour."""
    return int(min(base * 4 ** max(attempt - 1, 0), 3600))


@dataclass(frozen=True, slots=True)
class RetryPlan:
    retry: bool
    delay_seconds: int = 0
    retry_at: datetime | None = None


def plan_retry(
    failure: Failure,
    attempt: int,
    *,
    max_attempts: int,
    base_delay: int,
    now: datetime | None = None,
) -> RetryPlan:
    """Pure: try again only for a temporary failure, and only while runs are left."""
    if not failure.temporary or attempt >= max_attempts:
        return RetryPlan(retry=False)
    delay = retry_delay_seconds(attempt, base_delay)
    start = now or datetime.now(UTC)
    return RetryPlan(retry=True, delay_seconds=delay, retry_at=start + timedelta(seconds=delay))
