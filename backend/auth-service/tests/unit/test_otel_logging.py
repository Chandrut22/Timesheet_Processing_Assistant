"""auth-service logs go through OpenTelemetry only: one handler on the root logger,
text (or JSON) lines on stdout, uvicorn included, and nothing sent without an
endpoint."""

import json
import logging
import warnings
from collections.abc import Iterator

import pytest

from src.config.settings import Settings, settings
from src.observability.logging import setup as otel_logging

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from opentelemetry.sdk._logs import LoggingHandler


@pytest.fixture(autouse=True)
def clean_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
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


def test_json_lines_on_stdout_with_uvicorn_included(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "otel_logs_console", True)
    monkeypatch.setattr(settings, "otel_logs_format", "json")
    uvicorn = logging.getLogger("uvicorn.error")
    uvicorn.addHandler(logging.StreamHandler())
    uvicorn.propagate = False
    otel_logging.setup_logging("auth-service", level="INFO")

    logging.getLogger("src.main").info("auth-service started")
    uvicorn.info("Application startup complete.")
    logging.getLogger("uvicorn.access").info("POST /auth/login 200")  # quiet

    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.strip()]
    assert [x["message"] for x in lines] == [
        "auth-service started",
        "Application startup complete.",
    ]
    assert {x["service"] for x in lines} == {"auth-service"}
    handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, LoggingHandler)
    ]
    assert len(handlers) == 1


def test_text_lines_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert Settings.model_fields["otel_logs_format"].default == "text"
    monkeypatch.setattr(settings, "otel_logs_console", True)
    monkeypatch.setattr(settings, "otel_logs_format", "text")
    otel_logging.setup_logging("auth-service", level="INFO")

    logging.getLogger("src.main").warning("auth-service started")

    line = capsys.readouterr().out.strip()
    assert line.endswith(" WARN  [src.main] auth-service started")
    assert not line.startswith("{")


def test_nothing_is_sent_without_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).otel_exporter_otlp_endpoint is None
    monkeypatch.setattr(settings, "otel_enabled", True)
    monkeypatch.setattr(settings, "otel_exporter_otlp_endpoint", None)
    assert len(otel_logging._processors()) == 1  # stdout only
    monkeypatch.setattr(
        settings, "otel_exporter_otlp_endpoint", "http://collector:4318"
    )
    assert len(otel_logging._processors()) == 2
