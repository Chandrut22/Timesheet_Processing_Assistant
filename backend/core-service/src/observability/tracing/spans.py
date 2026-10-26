"""Spans for the pipeline steps, and the current trace id for the step log.

Uses only the OpenTelemetry API: with tracing off these are no-ops (no ids, no cost).

Rule: attributes are ids, counts, sizes, codes and timings. Never names, hours, file
names, email or document text (trace backends are less protected than the database)."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span

tracer = trace.get_tracer("timesheet.core")

AttributeValue = str | bool | int | float


def _clean(attributes: dict[str, Any]) -> dict[str, AttributeValue]:
    """Drop None; turn UUIDs and other objects into strings."""
    clean: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        clean[key] = value if isinstance(value, str | bool | int | float) else str(value)
    return clean


@contextmanager
def pipeline_span(name: str, **attributes: Any) -> Iterator[Span]:
    """A child span of whatever is current (the Celery task, the request, ...).
    An exception inside is recorded on the span and re-raised unchanged."""
    with tracer.start_as_current_span(name, attributes=_clean(attributes)) as span:
        yield span


def now_ns() -> int:
    return time.time_ns()


def finished_span(name: str, started_ns: int, **attributes: Any) -> None:
    """Record a short step that already ran (from started_ns until now) as a child of
    the current span: for steps inside a loop, without re-indenting the loop body."""
    span = tracer.start_span(name, start_time=started_ns, attributes=_clean(attributes))
    span.end()


def set_attributes(**attributes: Any) -> None:
    """Add attributes to the current span (e.g. ids known only after a flush)."""
    trace.get_current_span().set_attributes(_clean(attributes))


def current_trace_id() -> str | None:
    """The current trace id as 32 hex characters (as the log records show it), or None when
    tracing is off or nothing is being traced."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")
