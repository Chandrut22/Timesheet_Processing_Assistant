"""Second batch of review fixes: bug.md #15 (time limits), #16 (AI retries),
#17 (database conflicts -> 409), #22 (uploaded files on disk, not in Redis)."""

import asyncio
import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.config.settings import Settings, settings
from src.core.services.failures import JobTooSlowError, explain
from src.data.clients import upload_buffer

# --- #22 upload store on disk ------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "upload_buffer_ttl_hours", 1)
    return tmp_path / "uploads"


def test_files_are_written_read_and_deleted(store: Path) -> None:
    doc = uuid.uuid4()
    data = bytes(range(256)) * 100  # binary, not text
    asyncio.run(upload_buffer.put_file(doc, data))
    assert (store / f"{doc}.bin").exists()
    assert asyncio.run(upload_buffer.get_file(doc)) == data
    asyncio.run(upload_buffer.delete_file(doc))
    assert asyncio.run(upload_buffer.get_file(doc)) is None
    asyncio.run(upload_buffer.delete_file(doc))  # deleting twice is fine
    assert not list(store.glob("*.tmp"))  # no half-written files left behind


def test_an_expired_file_is_not_returned(store: Path) -> None:
    doc = uuid.uuid4()
    asyncio.run(upload_buffer.put_file(doc, b"%PDF-1.7"))
    old = time.time() - 2 * 3600
    os.utime(store / f"{doc}.bin", (old, old))
    assert asyncio.run(upload_buffer.get_file(doc)) is None
    assert not (store / f"{doc}.bin").exists()


def test_the_sweeper_purges_only_old_files(store: Path) -> None:
    old_doc, new_doc = uuid.uuid4(), uuid.uuid4()
    asyncio.run(upload_buffer.put_file(old_doc, b"old"))
    asyncio.run(upload_buffer.put_file(new_doc, b"new"))
    old = time.time() - 2 * 3600
    os.utime(store / f"{old_doc}.bin", (old, old))
    (store / "notes.txt").write_text("not ours")
    assert asyncio.run(upload_buffer.purge_expired()) == 1
    assert asyncio.run(upload_buffer.get_file(new_doc)) == b"new"
    assert (store / "notes.txt").exists()


# --- #15 time limits
# --------------------------------------------------------------------


def test_a_job_that_is_too_slow_is_not_retried() -> None:
    failure = explain(JobTooSlowError(1500))
    assert failure.temporary is False
    assert "longer than 25 minutes" in failure.message


def test_worker_times_must_be_in_order() -> None:
    Settings(_env_file=None)  # the defaults are valid
    with pytest.raises(ValidationError, match="WORKER_JOB_TIMEOUT_SECONDS"):
        Settings(_env_file=None, worker_stale_after_seconds=600)  # shorter than a job
    with pytest.raises(ValidationError):
        Settings(_env_file=None, broker_visibility_timeout_seconds=1000)


def test_celery_uses_the_limits() -> None:
    from src.control.workers.celery_app import celery_app

    conf: Any = celery_app.conf
    assert conf.task_time_limit == settings.worker_hard_time_limit_seconds
    assert (
        conf.broker_transport_options["visibility_timeout"]
        == settings.broker_visibility_timeout_seconds
    )
    assert conf.broker_transport_options["global_keyprefix"] == "core:celery:"


# --- #16 AI retries -------------------------------------------------------------------


def test_ai_client_retries_are_small_by_default() -> None:
    assert Settings(_env_file=None).llm_max_retries == 1


# --- #17 database conflicts
# -------------------------------------------------------------


class _OrigError(Exception):
    def __init__(self, text: str, constraint: str | None = None) -> None:
        super().__init__(text)
        self.constraint_name = constraint


def conflict(text: str, constraint: str | None = None) -> IntegrityError:
    return IntegrityError("INSERT ...", {}, _OrigError(text, constraint))


def test_conflict_messages_name_the_problem() -> None:
    from src.api.middleware.error_handler import GENERIC_CONFLICT, conflict_message

    assert "only once" in conflict_message(conflict("dup", "uq_timesheet_entries_day"))
    assert "code already exists" in conflict_message(
        conflict(
            'duplicate key value violates unique constraint "uq_employees_company_code"'
        )
    )
    assert (
        conflict_message(conflict("violates check constraint ck_x")) == GENERIC_CONFLICT
    )


def test_integrity_error_becomes_409() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.middleware.error_handler import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/boom")
    async def boom() -> None:
        raise conflict("dup", "uq_companies_name_lower")

    response = TestClient(app).post("/boom")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A company with this name already exists.",
        "code": "conflict",
    }
