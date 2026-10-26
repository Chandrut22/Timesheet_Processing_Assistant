"""Who is changing the database right now, for users.created_by / updated_by.

Set per request from the signed-in user (api/rest/dependencies.get_current_user), and
to the user themself when they sign in or reset their password. Never set = NULL =
the system (the seed script). A context variable, so concurrent requests never see
each other's user."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

current_actor: ContextVar[uuid.UUID | None] = ContextVar("current_actor", default=None)


def current_actor_id() -> uuid.UUID | None:
    """The user id of whoever is acting, or None for the system."""
    return current_actor.get()


@contextmanager
def acting_as(user_id: uuid.UUID | None) -> Iterator[None]:
    """Changes inside the block are recorded as made by `user_id` (tests, scripts)."""
    token = current_actor.set(user_id)
    try:
        yield
    finally:
        current_actor.reset(token)
