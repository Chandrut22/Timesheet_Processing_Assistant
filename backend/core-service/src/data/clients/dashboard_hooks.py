"""Tell the dashboard something changed, in every process that writes to the database.

A commit that inserted, updated or deleted a submission, timesheet or document publishes
one tiny message on a Redis channel. It runs AFTER the commit, so a reader that reacts to
the message always sees the new rows. Importing this module registers the hooks (it is
imported at the bottom of postgres.py). Statements that bypass the ORM are not seen; the
hub's periodic refresh covers those.
"""

import logging

import redis
from sqlalchemy import event
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.data.clients.redis import redis_key

logger = logging.getLogger(__name__)

WATCHED_TABLES = frozenset({"submissions", "timesheets", "documents"})
CHANNEL = redis_key("dashboard", "changed")

_publisher: redis.Redis | None = None
_registered = False


def _publish() -> None:
    """One PUBLISH (well under a millisecond). Never lets a Redis problem break a commit."""
    global _publisher
    try:
        if _publisher is None:
            _publisher = redis.Redis.from_url(
                settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5
            )
        _publisher.publish(CHANNEL, "1")
    except Exception:
        logger.warning("Could not tell the dashboard about a change", exc_info=True)


def _touches_watched(session: Session) -> bool:
    return any(
        getattr(obj, "__tablename__", None) in WATCHED_TABLES
        for group in (session.new, session.dirty, session.deleted)
        for obj in group
    )


def register() -> None:
    global _registered
    if _registered:
        return
    _registered = True

    @event.listens_for(Session, "after_flush")
    def _flushed(session: Session, _ctx: object) -> None:
        if _touches_watched(session):
            session.info["dashboard_dirty"] = True

    @event.listens_for(Session, "do_orm_execute")
    def _bulk(state) -> None:  # ORM bulk insert/update/delete statements
        mapper = state.bind_mapper
        if (
            (state.is_insert or state.is_update or state.is_delete)
            and mapper is not None
            and mapper.local_table.name in WATCHED_TABLES
        ):
            state.session.info["dashboard_dirty"] = True

    @event.listens_for(Session, "after_commit")
    def _committed(session: Session) -> None:
        if session.info.pop("dashboard_dirty", False):
            _publish()

    @event.listens_for(Session, "after_soft_rollback")
    def _rolled_back(session: Session, _previous: object) -> None:
        session.info.pop("dashboard_dirty", None)


register()