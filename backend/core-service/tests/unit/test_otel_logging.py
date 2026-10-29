"""Logs go through OpenTelemetry only: one handler on the root logger, normal text
lines (or JSON lines) on stdout, library loggers included, chatty ones quiet, an
unreachable collector never slows anything down, and a forked worker gets its own
provider."""

import importlib
import importlib.util
import json
import logging
import os
import pkgutil
import re
import time
import warnings
from collections.abc import Iterator

import pytest
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)

from src.config.settings import settings
from src.observability.logging import setup as otel_logging

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from opentelemetry.sdk._logs import LoggingHandler


@pytest.fixture(autouse=True)
def clean_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Each test starts with no provider and gets the root logger back afterwards."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    monkeypatch.setattr(otel_logging, "_provider", None)
    monkeypatch.setattr(otel_logging, "_handler", None)
    monkeypatch.setattr(otel_logging, "_pid", None)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def memory() -> tuple[InMemoryLogRecordExporter, list[SimpleLogRecordProcessor]]:
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    return exporter, [SimpleLogRecordProcessor(exporter)]


def test_every_record_becomes_a_normal_text_line_on_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "otel_logs_console", True)
    monkeypatch.setattr(settings, "otel_logs_format", "text")
    monkeypatch.setattr(settings, "otel_enabled", False)
    otel_logging.setup_logging("core-worker", level="INFO")
    log = logging.getLogger("src.core.services.processing_service")
    log.info("Submission %s processed", "1234", extra={"submission_id": "1234"})
    try:
        raise ValueError("model said no")
    except ValueError:
        log.exception("Extraction failed")
    log.debug("not shown at INFO")

    out = capsys.readouterr().out
    lines = out.splitlines()
    first = lines[0]
    assert re.fullmatch(
        r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} INFO  "
        r"\[src\.core\.services\.processing_service\] Submission 1234 processed"
        r"  submission_id=1234",
        first,
    )
    assert "code.file.path" not in out  # where the call was made is left out
    assert "{" not in first  # not JSON
    assert re.search(
        r" ERROR \[src\.core\.services\.processing_service\] Extraction failed$",
        lines[1],
    )
    # the traceback follows on its own lines, as Python's logging prints it
    assert lines[2] == "Traceback (most recent call last):"
    assert lines[-1] == "ValueError: model said no"
    assert "not shown at INFO" not in out


def test_json_format_gives_one_json_line_per_record(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "otel_logs_console", True)
    monkeypatch.setattr(settings, "otel_logs_format", "json")
    monkeypatch.setattr(settings, "otel_enabled", False)
    otel_logging.setup_logging("core-worker", level="INFO")
    log = logging.getLogger("src.core.services.processing_service")
    log.info("Submission %s processed: %s", "1234", "approved")
    try:
        raise ValueError("model said no")
    except ValueError:
        log.exception("Extraction failed")
    log.debug("not shown at INFO")

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2  # one line each, the stack trace inside the JSON
    first, second = (json.loads(line) for line in lines)
    assert first["message"] == "Submission 1234 processed: approved"
    assert (first["level"], first["service"]) == ("INFO", "core-worker")
    assert first["logger"] == "src.core.services.processing_service"
    assert first["attributes"]["code.line.number"] > 0
    assert "trace_id" not in first  # not inside a request or job
    assert second["level"] == "ERROR"
    assert second["attributes"]["exception.type"] == "ValueError"
    assert "model said no" in second["attributes"]["exception.stacktrace"]


def test_one_otel_handler_on_the_root_and_libraries_go_through_it() -> None:
    root = logging.getLogger()
    plain = logging.StreamHandler()
    root.addHandler(plain)  # what basicConfig would have added
    uvicorn = logging.getLogger("uvicorn.error")
    uvicorn.addHandler(logging.StreamHandler())
    uvicorn.propagate = False  # as uvicorn sets it up
    exporter, processors = memory()

    otel_logging.setup_logging("core-service", processors=processors)
    otel_logging.setup_logging(
        "core-service", processors=processors
    )  # twice: no change

    assert plain not in root.handlers
    assert [type(h) for h in root.handlers].count(LoggingHandler) == 1
    uvicorn.info("Application startup complete.")
    logging.getLogger("sqlalchemy.pool").warning("connection invalidated")
    bodies = [r.log_record.body for r in exporter.get_finished_logs()]
    assert bodies == ["Application startup complete.", "connection invalidated"]
    assert uvicorn.handlers == [] and uvicorn.propagate is True


def test_chatty_libraries_only_send_warnings() -> None:
    exporter, processors = memory()
    otel_logging.setup_logging("core-service", processors=processors)
    logging.getLogger("uvicorn.access").info("GET /health 200")  # every 10 s
    logging.getLogger("httpx").info("HTTP Request: POST https://ollama.com/v1/chat")
    logging.getLogger("celery.app.trace").info("Task core.process succeeded in 2.1s")
    logging.getLogger("httpx").warning("retrying")
    assert [r.log_record.body for r in exporter.get_finished_logs()] == ["retrying"]


def test_an_unreachable_collector_never_slows_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "otel_logs_console", False)
    monkeypatch.setattr(settings, "otel_enabled", True)
    monkeypatch.setattr(settings, "otel_exporter_otlp_endpoint", "http://127.0.0.1:9")
    otel_logging.setup_logging("core-service")
    log = logging.getLogger("src.test")
    started = time.monotonic()
    for number in range(200):
        log.info("line %d", number)
    assert time.monotonic() - started < 1.0  # batched in the background
    started = time.monotonic()
    otel_logging.flush_logs()  # bounded, never raises
    assert time.monotonic() - started < 4.0


def test_the_collector_is_used_only_when_enabled_and_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "otel_logs_console", True)
    monkeypatch.setattr(settings, "otel_enabled", True)
    monkeypatch.setattr(settings, "otel_exporter_otlp_endpoint", None)
    assert len(otel_logging._processors()) == 1  # stdout only
    monkeypatch.setattr(
        settings, "otel_exporter_otlp_endpoint", "http://collector:4318"
    )
    assert len(otel_logging._processors()) == 2
    monkeypatch.setattr(settings, "otel_enabled", False)
    assert len(otel_logging._processors()) == 1


def test_a_forked_worker_gets_its_own_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _, processors = memory()
    parent = otel_logging.setup_logging("core-worker", processors=processors)
    assert otel_logging.setup_logging("core-worker") is parent  # same process
    monkeypatch.setattr(os, "getpid", lambda: -1)  # as after a fork
    assert (
        otel_logging.setup_logging("core-worker", processors=processors) is not parent
    )


def test_the_logging_package_is_the_opentelemetry_setup() -> None:
    """observability/logging/ holds only the OpenTelemetry setup (the old text logging
    with its own formatters and handlers is gone)."""
    package = importlib.import_module("src.observability.logging")
    assert sorted(m.name for m in pkgutil.iter_modules(package.__path__)) == ["setup"]
    assert callable(otel_logging.setup_logging) and callable(otel_logging.flush_logs)


def test_opentelemetry_own_warnings_never_loop_through_the_exporter() -> None:
    exporter, processors = memory()
    otel_logging.setup_logging("core-service", processors=processors)
    own = logging.getLogger("opentelemetry.exporter.otlp.proto.http._log_exporter")
    own.warning("Failed to export logs batch")  # would be exported, fail, log again...
    assert exporter.get_finished_logs() == ()
    assert logging.getLogger("opentelemetry").propagate is False


def test_celery_leaves_logging_to_opentelemetry() -> None:
    from celery.signals import setup_logging as celery_setup_logging

    from src.control.workers import celery_app

    # With a receiver on this signal, Celery does not set up its own handlers.
    receivers = [ref() for _, ref in celery_setup_logging.receivers]
    assert celery_app._logs_through_opentelemetry in receivers
