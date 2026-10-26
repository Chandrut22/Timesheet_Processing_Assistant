# Development commands (needs make: Git Bash, WSL, or `choco install make` on Windows).
# Every target is one `uv run` command: see docs/runbook.md for the PowerShell versions.
.PHONY: install lint format typecheck test check migrate revision run worker email

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src tests

test:
	uv run pytest

check: lint typecheck test
	uv run ruff format --check .

migrate:
	uv run alembic upgrade head

revision:  # make revision m="what changed"
	uv run alembic revision --autogenerate -m "$(m)"

run:
	uv run uvicorn src.main:app --reload --port 8002

worker:
	uv run celery -A src.control.workers.celery_app worker -Q timesheets -l info

email:
	uv run python -m src.control.workers.email_listener
