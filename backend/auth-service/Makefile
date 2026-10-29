# Development commands (needs make: Git Bash, WSL, or `choco install make` on Windows).
# Every target is one `uv run` command: see docs/runbook.md for the PowerShell versions.
.PHONY: install lint format typecheck test check validate audit migrate revision run keys

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

validate: lint typecheck test
	uv run ruff format --check .

migrate:
	uv run alembic upgrade head

revision:  # make revision m="what changed"
	uv run alembic revision --autogenerate -m "$(m)"

run:
	uv run uvicorn src.main:app --reload --port 8001

keys:
	uv run python scripts/generate_keys.py

audit:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
