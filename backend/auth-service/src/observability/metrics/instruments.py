"""What auth-service measures (OpenTelemetry metrics, see setup.py).

Instruments come from the global meter: before setup_metrics() (or without a collector)
they are no-ops, afterwards they record into the real provider."""

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter, UpDownCounter

METER_NAME = "timesheet.auth-service"


def _meter(meter: Meter | None = None) -> Meter:
    return meter or metrics.get_meter(METER_NAME)


def http_instruments(
    meter: Meter | None = None,
) -> tuple[Counter, Histogram, UpDownCounter]:
    m = _meter(meter)
    return (
        m.create_counter(
            "http.server.requests", unit="{request}", description="HTTP requests"
        ),
        m.create_histogram(
            "http.server.duration", unit="ms", description="Request time"
        ),
        m.create_up_down_counter(
            "http.server.active_requests",
            unit="{request}",
            description="Requests in flight",
        ),
    )


# Sign-ins by result ("success" / "failed"): a spike of failures is worth an alert.
logins = _meter().create_counter(
    "auth.logins", unit="{login}", description="Sign-in attempts by result"
)
