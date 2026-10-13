# core-service image: used by core-migrate, core-service (API) and core-worker.
FROM python:3.13-slim

# Docling (PDF/image rendering + OCR) needs these system libraries.
# apt over HTTPS: some networks block plain HTTP (port 80) to the Debian mirrors.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0t64 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/models/hf

# Dependencies first (cached layer): only rebuilt when pyproject.toml / uv.lock change.
# torch comes from the CPU-only index set in pyproject.toml (no multi-GB CUDA build).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY src ./src


# Run as a normal user, not root. The code and .venv stay root-owned (read-only for
# the app is fine); only /models must be writable, for Docling's model cache.
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /models/hf \
 && chown app:app /models /models/hf
USER app

EXPOSE 8002
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]