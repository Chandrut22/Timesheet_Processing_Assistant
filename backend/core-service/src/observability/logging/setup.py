"""Logs, through OpenTelemetry only.

The code keeps calling `logging.getLogger(__name__).info(...)`, the way OpenTelemetry's
Python docs say to (its logs API is meant for bridges, not for application code). The
root logger has ONE handler, OpenTelemetry's LoggingHandler, which turns every record
(ours and the libraries': uvicorn, SQLAlchemy, Celery, httpx, ...) into an OpenTelemetry
log record with the service name, the severity, the file and line, any exception with
its stack trace, and the trace and span ids when it is written inside a request or a
job.

Where the records go:
  - stdout (OTEL_LOGS_CONSOLE, on by default), so `docker compose logs` shows
    everything: a normal text line per record (OTEL_LOGS_FORMAT=text, the default), or
    one JSON object per line (OTEL_LOGS_FORMAT=json, for a log shipper). Written
    straight away: nothing is lost when a process dies.
  - an OpenTelemetry Collector (or Grafana, SigNoz, ...) as well, when OTEL_ENABLED and
    OTEL_EXPORTER_OTLP_ENDPOINT are set: batched and sent in the background, with a
    short timeout. If it is down, the batch is dropped; requests and jobs never wait.

Log messages should carry ids and counts, never names, hours, email or document text."""

import contextlib
import json
import logging
import os
import sys
import threading
import warnings
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import IO, Any, cast

from opentelemetry.sdk._logs import (
    LoggerProvider,
    LogRecordProcessor,
    ReadableLogRecord,
)
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.resources import Resource

from src.config.settings import settings

# opentelemetry-sdk 1.44 marks its LoggingHandler as moving to the
# opentelemetry-instrumentation-logging package; it is the same handler and still part
# of the SDK pinned here. Switch the import when that package is added to
# pyproject.toml.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from opentelemetry.sdk._logs import LoggingHandler

# Libraries that log every request or task at INFO: only their warnings are kept.
# (Requests and jobs are already traced, and the step log records every step.)
QUIET_LOGGERS = (
    "uvicorn.access",  # one line per request, health checks every 10 s included
    "httpx",
    "httpcore",
    "urllib3",
    "celery.app.trace",  # "Task ... succeeded in 2.1s"
    "celery.worker.strategy",  # "Task ... received"
    "docling",
    "RapidOCR",
)
# Loggers that come with their own handler (uvicorn sets these up before importing the
# app): their handlers are removed so they go through the root logger, and so through
# OpenTelemetry, like everything else.
OWN_HANDLER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# OpenTelemetry's own warnings ("Failed to export logs batch ...") cannot go through
# OpenTelemetry: each failed export would log a record that is exported, fails, and logs
# again. They get a plain stderr line instead, warnings and errors only.
SELF_LOGGER = "opentelemetry"

# Record attributes left out of the stdout line (uvicorn's copy of the message with
# terminal colour codes).
NOT_SHOWN = frozenset({"color_message"})

_provider: LoggerProvider | None = None
_handler: LoggingHandler | None = None
_pid: int | None = None


class _Stdout:
    """sys.stdout as it is at write time (tests and Celery replace sys.stdout)."""

    def write(self, text: str) -> int:
        return sys.stdout.write(text)

    def flush(self) -> None:
        sys.stdout.flush()


def one_line(record: ReadableLogRecord) -> str:
    """A log record as one compact JSON line: what a person reading `docker compose
    logs` needs, without repeating the resource on every line."""
    log = record.log_record
    timestamp = log.timestamp or log.observed_timestamp or 0
    line: dict[str, Any] = {
        "time": datetime.fromtimestamp(timestamp / 1e9, UTC).isoformat(
            timespec="milliseconds"
        ),
        "level": log.severity_text,
        "service": record.resource.attributes.get("service.name"),
        "logger": record.instrumentation_scope.name
        if record.instrumentation_scope
        else None,
        "message": log.body if isinstance(log.body, str) else str(log.body),
    }
    if log.trace_id:
        line["trace_id"] = f"{log.trace_id:032x}"
        line["span_id"] = f"{log.span_id:016x}"
    attributes = {k: v for k, v in (log.attributes or {}).items() if k not in NOT_SHOWN}
    if attributes:
        line["attributes"] = attributes
    return json.dumps(line, default=str, ensure_ascii=False) + "\n"


# Attributes the text line leaves out: where the call was made (code.*) and the
# exception, which is printed below the line as a normal traceback.
TEXT_HIDDEN_PREFIXES = ("code.", "exception.")


def text_line(record: ReadableLogRecord) -> str:
    """A log record as a normal log line, the way Python's logging prints it:

        2026-10-24 06:25:15.458 INFO  [celery.apps.worker] celery@2150 ready.

    Extra attributes follow as key=value, the trace id when the line was written inside
    a request or job, and an exception's traceback on the lines below."""
    log = record.log_record
    timestamp = log.timestamp or log.observed_timestamp or 0
    when = datetime.fromtimestamp(timestamp / 1e9, UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
    logger = record.instrumentation_scope.name if record.instrumentation_scope else "-"
    message = log.body if isinstance(log.body, str) else str(log.body)
    line = f"{when[:-3]} {(log.severity_text or '-'):<5} [{logger}] {message}"
    attributes = log.attributes or {}
    extras = [
        key + "=" + str(value)
        for key, value in attributes.items()
        if key not in NOT_SHOWN and not key.startswith(TEXT_HIDDEN_PREFIXES)
    ]
    if extras:
        line += "  " + " ".join(extras)
    if log.trace_id:
        line += f"  trace_id={log.trace_id:032x}"
    stacktrace = attributes.get("exception.stacktrace")
    if stacktrace:
        line += "\n" + str(stacktrace).rstrip()
    return line + "\n"


def _processors() -> list[LogRecordProcessor]:
    processors: list[LogRecordProcessor] = []
    if settings.otel_logs_console:
        formatter = one_line if settings.otel_logs_format == "json" else text_line
        exporter = ConsoleLogRecordExporter(
            out=cast(IO[str], _Stdout()), formatter=formatter
        )
        processors.append(SimpleLogRecordProcessor(exporter))
    if settings.otel_enabled and settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

        endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/logs"
        processors.append(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, timeout=5))
        )
    return processors


def setup_logging(
    service_name: str | None = None,
    *,
    level: str | None = None,
    processors: Sequence[LogRecordProcessor] | None = None,
    force: bool = False,
) -> LoggerProvider:
    """Send every log record of this process to OpenTelemetry. Safe to call twice; a
    forked process (a Celery worker) gets its own provider. `processors` replaces the
    exporters (tests pass an in-memory one)."""
    global _provider, _handler, _pid
    if _provider is not None and _pid == os.getpid() and not force:
        return _provider

    provider = LoggerProvider(
        resource=Resource.create(
            {
                "service.name": service_name or settings.otel_service_name,
                "service.namespace": "timesheet",
                "deployment.environment": settings.environment,
            }
        )
    )
    chosen = list(processors) if processors is not None else _processors()
    for processor in chosen:
        provider.add_log_record_processor(processor)
    with warnings.catch_warnings():  # the same deprecation as at the import above
        warnings.simplefilter("ignore", DeprecationWarning)
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=provider)

    root = logging.getLogger()
    for old in list(root.handlers):
        # Ours from an earlier call, and plain stream handlers (basicConfig, Celery's).
        # Other handlers (pytest's capture) are left alone.
        if (
            old is _handler
            or isinstance(old, LoggingHandler)
            or type(old) is logging.StreamHandler
        ):
            root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel((level or settings.log_level).upper())

    for name in OWN_HANDLER_LOGGERS:
        own = logging.getLogger(name)
        for old in list(own.handlers):
            own.removeHandler(old)
        own.propagate = True
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _own_diagnostics_to_stderr()

    _provider, _handler, _pid = provider, handler, os.getpid()
    if not chosen:
        sys.stderr.write(
            "Logging: OTEL_LOGS_CONSOLE is false and no OTLP endpoint is set, so log "
            "records go nowhere.\n"
        )
    return provider


def _own_diagnostics_to_stderr() -> None:
    own = logging.getLogger(SELF_LOGGER)
    own.propagate = False
    own.setLevel(logging.WARNING)
    if not own.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        own.addHandler(handler)


def flush_logs(timeout_s: float = 3.0) -> None:
    """Send what is still batched for the collector, waiting at most `timeout_s`.
    The SDK's force_flush ignores its own timeout (opentelemetry-python #4568) and can
    retry an unreachable collector for a long time, so it runs in a daemon thread that
    is simply left behind if it takes too long."""
    provider = _provider
    if provider is None:
        return

    def flush() -> None:
        with contextlib.suppress(Exception):  # never let logging break a shutdown
            provider.force_flush()

    worker = threading.Thread(target=flush, name="otel-log-flush", daemon=True)
    worker.start()
    worker.join(timeout_s)
