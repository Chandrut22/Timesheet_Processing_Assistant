"""core-service entry point: `uvicorn src.main:app` (the app itself is in api/rest/app.py).

The Celery worker and the email listener have their own entry points in control/workers/."""

from src.observability.logging.setup import setup_logging

setup_logging()  # first: every log record (ours and the libraries') goes through OpenTelemetry

from src.api.rest.app import create_app  # noqa: E402  (after logging is set up)

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8002)  # noqa: S104
