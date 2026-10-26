"""What core-service measures (OpenTelemetry metrics, see setup.py).

Instruments come from the global meter: before setup_metrics() (or without a collector)
they are no-ops, afterwards they record into the real provider. The API process and the
Celery worker each set up their own provider (service.name core-service / core-worker)."""

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter, UpDownCounter

METER_NAME = "timesheet.core-service"


def _meter(meter: Meter | None = None) -> Meter:
    return meter or metrics.get_meter(METER_NAME)


def http_instruments(meter: Meter | None = None) -> tuple[Counter, Histogram, UpDownCounter]:
    m = _meter(meter)
    return (
        m.create_counter("http.server.requests", unit="{request}", description="HTTP requests"),
        m.create_histogram("http.server.duration", unit="ms", description="Request time"),
        m.create_up_down_counter(
            "http.server.active_requests", unit="{request}", description="Requests in flight"
        ),
    )


# Business counters (written by the worker).
timesheets_extracted = _meter().create_counter(
    "timesheet.extracted", unit="{timesheet}", description="Timesheets the AI extracted"
)
submissions_failed = _meter().create_counter(
    "timesheet.submissions_failed",
    unit="{submission}",
    description="Submissions that failed (reason: temporary / permanent)",
)
