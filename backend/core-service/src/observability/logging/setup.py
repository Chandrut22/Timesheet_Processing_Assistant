import logging

from src.config.settings import settings
from src.observability.tracing.spans import current_trace_id

PLAIN_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
# With tracing on, every line says which trace it belongs to (search it in Jaeger).
TRACE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s [trace=%(trace_id)s]: %(message)s"


class TraceIdFilter(logging.Filter):
    """Adds record.trace_id: the current OpenTelemetry trace, or "-"."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id() or "-"
        return True


def log_format() -> str:
    return TRACE_FORMAT if settings.otel_enabled else PLAIN_FORMAT


def add_trace_ids(logger: logging.Logger) -> None:
    """Put trace ids on a logger's existing handlers (Celery sets up its own)."""
    for handler in logger.handlers:
        handler.addFilter(TraceIdFilter())
        handler.setFormatter(logging.Formatter(log_format()))


def configure_logging(level: str = "INFO") -> None:
    """Plain text logs on stdout (with the trace id when tracing is on)."""
    logging.basicConfig(level=level.upper(), format=log_format())
    for handler in logging.getLogger().handlers:
        handler.addFilter(TraceIdFilter())
