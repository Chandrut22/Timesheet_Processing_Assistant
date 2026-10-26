"""OpenTelemetry metrics: the meter provider and its exporter.

Metrics leave the process only when OTEL_ENABLED and OTEL_EXPORTER_OTLP_ENDPOINT are set
(the same collector as traces and logs, at <endpoint>/v1/metrics, every 60 seconds).
Otherwise the OpenTelemetry API's no-op meter is used: recording costs next to nothing.
No new package: the SDK and the OTLP exporter are already dependencies."""

import contextlib
import logging

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from src.config.settings import settings

logger = logging.getLogger(__name__)
EXPORT_EVERY_MS = 60_000

_provider: MeterProvider | None = None


def setup_metrics(service_name: str | None = None) -> MeterProvider | None:
    """Install the meter provider (once). None = metrics stay in-process no-ops."""
    global _provider
    if _provider is not None:
        return _provider
    if not (settings.otel_enabled and settings.otel_exporter_otlp_endpoint):
        return None
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/metrics"
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, timeout=5), export_interval_millis=EXPORT_EVERY_MS
    )
    _provider = MeterProvider(
        resource=Resource.create(
            {
                "service.name": service_name or settings.otel_service_name,
                "service.namespace": "timesheet",
                "deployment.environment": settings.environment,
            }
        ),
        metric_readers=[reader],
    )
    metrics.set_meter_provider(_provider)
    logger.info("Metrics are sent to %s", endpoint)
    return _provider


def shutdown_metrics() -> None:
    """Send what is left and stop (never lets metrics break a shutdown)."""
    if _provider is not None:
        with contextlib.suppress(Exception):
            _provider.shutdown(timeout_millis=3000)
