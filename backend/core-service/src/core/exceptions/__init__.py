"""App errors. Raise these anywhere; one handler turns them into JSON responses."""


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ConfirmationRequiredError(ConflictError):
    """The action would undo something people did (e.g. approvals): ask first, then
    repeat the request with the confirmation flag the message names."""

    code = "confirmation_required"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class TooManyRequestsError(AppError):
    """Asked again too soon (pass Retry-After in headers)."""

    status_code = 429
    code = "too_many_requests"


class ServiceUnavailableError(AppError):
    """A part of the system the request needs is not running right now."""

    status_code = 503
    code = "service_unavailable"
