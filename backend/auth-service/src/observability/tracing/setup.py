"""OpenTelemetry tracing for auth-service: one span per request, plus SQL and Redis.

Off unless OTEL_ENABLED=true. When on, log records written inside a request carry its
trace id (observability/logging/setup.py). Spans leave the process only when OTEL_EXPORTER_OTLP_ENDPOINT
is set (an OpenTelemetry Collector); if it is down they are dropped and sign-in is never
slowed down. Request spans keep the path but not the
query string, and never carry passwords, tokens or request bodies."""

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
EXCLUDED_URLS = "health,health/db"


def without_query(span: Any, scope: dict[str, Any]) -> None:
    """Drop the query string (user searches can hold emails)."""
    if span is None or not span.is_recording():
        return
    path = scope.get("path", "")
    host = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1")
    span.set_attribute("http.target", path)
    span.set_attribute("url.query", "")
    if host:
        span.set_attribute("http.url", f"{scope.get('scheme', 'http')}://{host}{path}")


def setup_tracing(
    *, app: Any = None, engine: Any = None, processor: SpanProcessor | None = None
) -> bool:
    """Turn tracing on (only if OTEL_ENABLED, or a test passes a processor)."""
    global _provider
    if (not settings.otel_enabled and processor is None) or _provider is not None:
        return _provider is not None
    if processor is None and settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=5))
    _provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.namespace": "timesheet",
                "deployment.environment": settings.environment,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(settings.otel_sample_ratio)),
    )
    if processor is not None:  # None: no endpoint, trace ids in logs only
        _provider.add_span_processor(processor)
    trace.set_tracer_provider(_provider)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        if app is not None:
            FastAPIInstrumentor.instrument_app(
                app, excluded_urls=EXCLUDED_URLS, server_request_hook=without_query
            )
        if engine is not None:
            SQLAlchemyInstrumentor().instrument(
                engine=getattr(engine, "sync_engine", engine)
            )
        RedisInstrumentor().instrument()
    except Exception:  # a broken instrumentation must not stop sign-in
        logger.warning("Could not set up tracing", exc_info=True)
    logger.info(
        "Tracing on: %s -> %s",
        settings.otel_service_name,
        settings.otel_exporter_otlp_endpoint or "trace ids in logs only (no endpoint)",
    )
    return True


def shutdown_tracing() -> None:
    global _provider
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:
            logger.warning("Could not flush traces", exc_info=True)
        _provider = None
