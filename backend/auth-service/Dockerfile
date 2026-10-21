FROM python:3.13-slim
# Pinned (never "latest"): the same uv version as core-service, so builds repeat.
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .

# Run as a normal user (uid 1000), not root. The code stays root-owned (read-only for
# the app); the JWT keys are mounted read-only at /app/keys by docker compose.
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
