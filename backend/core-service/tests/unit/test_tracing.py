"""OpenTelemetry tracing: off by default, spans nest, trace ids reach the step log,
and no query strings (names, emails) end up in request spans."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.config.settings import Settings, settings
from src.constants.timesheet_status import StepName, StepResult
from src.core.services.activity_log import record_step
from src.observability.logging.setup import TraceIdFilter
from src.observability.tracing import setup as tracing
from src.observability.tracing.spans import (
    current_trace_id,
    finished_span,
    now_ns,
    pipeline_span,
)

EXPORTER = InMemorySpanExporter()
APP = FastAPI()


@APP.get("/timesheets")
async def search() -> dict[str, str]:
    return {"ok": "yes"}


@APP.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)


def test_tracing_is_off_by_default() -> None:
    assert Settings(_env_file=None).otel_enabled is False
    assert tracing.setup_tracing() is False  # nothing set up, nothing exported
    assert current_trace_id() is None
    session = FakeSession()
    record_step(
        session,  # type: ignore[arg-type]
        submission_id=uuid.uuid4(),
        step=StepName.READ,
        result=StepResult.SUCCESS,
        message="Read t.pdf",
    )
    assert session.added[0].trace_id is None  # type: ignore[attr-defined]


@pytest.fixture(scope="module")
def traced() -> Iterator[InMemorySpanExporter]:
    """Tracing on for the rest of this module, exporting to memory."""
    assert tracing.setup_tracing("core-test", app=APP, processor=SimpleSpanProcessor(EXPORTER))
    tracing.setup_tracing("core-test", app=APP)  # a second call changes nothing
    yield EXPORTER


def test_spans_nest_and_the_trace_id_reaches_the_step_log(traced: InMemorySpanExporter) -> None:
    traced.clear()
    session = FakeSession()
    submission_id = uuid.uuid4()
    with pipeline_span("submission.process", submission_id=submission_id, run=1):
        trace_id = current_trace_id()
        with pipeline_span("document.read", document_id=uuid.uuid4(), size_bytes=1234):
            record_step(
                session,  # type: ignore[arg-type]
                submission_id=submission_id,
                step=StepName.READ,
                result=StepResult.SUCCESS,
                message="Read t.pdf",
            )
        started = now_ns()
        finished_span("timesheet.decide", started, status="approved", reviewer=None)

    assert trace_id is not None and len(trace_id) == 32
    assert session.added[0].trace_id == trace_id  # type: ignore[attr-defined]
    spans = {s.name: s for s in traced.get_finished_spans()}
    root = spans["submission.process"]
    assert spans["document.read"].parent.span_id == root.context.span_id  # type: ignore[union-attr]
    assert spans["timesheet.decide"].parent.span_id == root.context.span_id  # type: ignore[union-attr]
    assert root.attributes["submission_id"] == str(submission_id)  # type: ignore[index]
    assert "reviewer" not in spans["timesheet.decide"].attributes  # type: ignore[operator]
    assert root.resource.attributes["service.name"] == "core-test"


def test_an_error_is_recorded_on_the_span(traced: InMemorySpanExporter) -> None:
    traced.clear()
    with pytest.raises(ValueError), pipeline_span("ai.extract"):
        raise ValueError("model said no")
    (span,) = traced.get_finished_spans()
    assert span.status.status_code.name == "ERROR"
    assert span.events[0].name == "exception"


def test_request_spans_drop_the_query_and_skip_health(traced: InMemorySpanExporter) -> None:
    traced.clear()
    client = TestClient(APP)
    client.get("/timesheets?q=Grace%20Okoye&sender=grace@example.com")
    client.get("/health")
    spans = traced.get_finished_spans()
    text = repr([dict(s.attributes or {}) for s in spans])
    assert "Grace" not in text and "grace@example.com" not in text
    assert any("/timesheets" in str((s.attributes or {}).get("http.target")) for s in spans)
    assert not any("/health" in str((s.attributes or {}).get("http.target")) for s in spans)


def test_log_lines_carry_the_trace_id(traced: InMemorySpanExporter) -> None:
    import logging

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    TraceIdFilter().filter(record)
    assert record.trace_id == "-"  # type: ignore[attr-defined]
    with pipeline_span("submission.process"):
        TraceIdFilter().filter(record)
        assert record.trace_id == current_trace_id()  # type: ignore[attr-defined]


def test_sample_ratio_is_validated() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, otel_sample_ratio=1.5)
    assert settings.otel_exporter_otlp_endpoint.startswith("http")
