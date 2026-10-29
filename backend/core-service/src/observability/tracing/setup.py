"""OpenTelemetry tracing: one trace per email or upload, across API -> queue -> worker.

Off unless OTEL_ENABLED=true. When off, nothing here runs and every span in the code is
a cheap no-op (the OpenTelemetry API's default). When on, every request and job has a
trace
id: log records written inside it carry that id (observability/logging/setup.py), and so
does each step-log row. Spans leave the process only when OTEL_EXPORTER_OTLP_ENDPOINT is
set (an OpenTelemetry Collector): batched, sent in the background, dropped if it is
down. Processing never waits for, or fails because of, tracing.

Spans carry ids, counts and timings only, never names, hours, email or document text.
The state log and step log in PostgreSQL remain the record of what happened."""

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from src.config.settings import settings

logger = logging.getLogger(__name__)

_provider: TracerProvider | None = None
_instrumented: set[str] = set()

# Requests we never trace (Docker health checks every 10 s would bury the real traces).
EXCLUDED_URLS = "health,health/db,health/redis"


def _exporter_processor() -> SpanProcessor | None:
    """The OTLP exporter, or None when no endpoint is set (trace ids only)."""
    if not settings.otel_exporter_otlp_endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
    # Short timeout: a missing collector costs a dropped batch, never a slow request.
    return BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=5))


def setup_tracing(
    service_name: str | None = None,
    *,
    app: Any = None,
    engine: Any = None,
    celery: bool = False,
    processor: SpanProcessor | None = None,
) -> bool:
    """Turn tracing on for this process. Returns False (and does nothing) when disabled.

    app      the FastAPI app: one span per request (health checks excluded)
    engine   the SQLAlchemy AsyncEngine: one span per query (SQL text, no parameters)
    celery   trace task publish + run, so a job continues the trace that queued it
    processor  tests pass an in-memory processor instead of the OTLP exporter

    Redis and httpx (the AI calls) are traced in every process. Safe to call twice."""
    global _provider
    if not settings.otel_enabled and processor is None:
        return False

    if _provider is None:
        resource = Resource.create(
            {
                "service.name": service_name or settings.otel_service_name,
                "service.namespace": "timesheet",
                "deployment.environment": settings.environment,
            }
        )
        _provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(settings.otel_sample_ratio)),
        )
        chosen = processor or _exporter_processor()
        if chosen is not None:
            _provider.add_span_processor(chosen)
        trace.set_tracer_provider(_provider)
        _instrument_once("redis", _instrument_redis)
        _instrument_once("httpx", _instrument_httpx)
        logger.info(
            "Tracing on: %s -> %s",
            service_name or settings.otel_service_name,
            settings.otel_exporter_otlp_endpoint
            or "trace ids in logs only (no endpoint)",
        )

    if app is not None:
        _instrument_once(f"fastapi:{id(app)}", lambda: _instrument_fastapi(app))
    if engine is not None:
        _instrument_once(
            f"sqlalchemy:{id(engine)}", lambda: _instrument_sqlalchemy(engine)
        )
    if celery:
        _instrument_once("celery", _instrument_celery)
    return True


def shutdown_tracing() -> None:
    """Send what is still buffered (best effort, a few seconds at most)."""
    global _provider
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:  # never let tracing break a shutdown
            logger.warning("Could not flush traces", exc_info=True)
        _provider = None


def _instrument_once(key: str, action: Any) -> None:
    if key in _instrumented:
        return
    try:
        action()
        _instrumented.add(key)
    except Exception:  # a broken instrumentation must not stop the app
        logger.warning("Could not set up tracing for %s", key, exc_info=True)


def without_query(span: Any, scope: dict[str, Any]) -> None:
    """Drop the query string from request spans: searches can hold names or emails
    (?q=..., ?sender=...). The route and path are enough to find a request."""
    if span is None or not span.is_recording():
        return
    path = scope.get("path", "")
    host = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1")
    span.set_attribute("http.target", path)
    span.set_attribute("url.query", "")
    if host:
        span.set_attribute("http.url", f"{scope.get('scheme', 'http')}://{host}{path}")


def _instrument_fastapi(app: Any) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app, excluded_urls=EXCLUDED_URLS, server_request_hook=without_query
    )


def _instrument_sqlalchemy(engine: Any) -> None:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    # The async engine runs on a sync engine underneath: that is where queries happen.
    SQLAlchemyInstrumentor().instrument(engine=getattr(engine, "sync_engine", engine))


def _instrument_redis() -> None:
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    RedisInstrumentor().instrument()


def _instrument_httpx() -> None:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()  # the AI provider calls (URL, status, time)


def _instrument_celery() -> None:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    CeleryInstrumentor().instrument()  # type: ignore[no-untyped-call]
