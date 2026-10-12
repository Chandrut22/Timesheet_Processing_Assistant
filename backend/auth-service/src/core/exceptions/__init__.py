"""App errors. Services raise these; one handler in main.py turns them into JSON.

Each error knows its HTTP status, so services never import FastAPI.
"""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """The request clashes with existing data (duplicate email, last super admin...)."""

    status_code = 409
    code = "conflict"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class TooManyRequestsError(AppError):
    """Rate limit or lockout. Retry-After tells the client how long to wait."""

    status_code = 429
    code = "too_many_requests"

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message, headers={"Retry-After": str(retry_after)})
        self.retry_after = retry_after
