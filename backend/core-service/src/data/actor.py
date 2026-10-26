"""Who is changing the database right now, for the created_by / updated_by columns.

Set once per API request from the verified token (api/rest/dependencies.get_principal).
Celery jobs, the email listener and the sweeper never set it, so their rows are
written with NULL = the system. A context variable, so concurrent requests and jobs
never see each other's user."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

current_actor: ContextVar[uuid.UUID | None] = ContextVar("current_actor", default=None)


def current_actor_id() -> uuid.UUID | None:
    """The auth-service user id of whoever is acting, or None for the system."""
    return current_actor.get()


@contextmanager
def acting_as(user_id: uuid.UUID | None) -> Iterator[None]:
    """Changes inside the block are recorded as made by `user_id` (tests, scripts)."""
    token = current_actor.set(user_id)
    try:
        yield
    finally:
        current_actor.reset(token)
