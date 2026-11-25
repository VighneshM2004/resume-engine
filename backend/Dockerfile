# syntax=docker/dockerfile:1
# Build context is the repository root (the uv workspace lives there).

# ---------- builder: resolve and install locked dependencies ----------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, sources second: editing code doesn't invalidate the
# (slow) dependency layer.
COPY pyproject.toml uv.lock ./
COPY engine/pyproject.toml engine/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
# Every workspace member's pyproject must exist for uv to read the lock;
# ml/ itself is not installed in this image.
COPY ml/pyproject.toml ml/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package backend --no-install-workspace

COPY engine/ engine/
COPY backend/ backend/
# --no-editable copies our packages into the venv, so the runtime image
# needs only the venv, not the source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package backend --no-editable

# ---------- runtime: venv only, non-root ----------
FROM python:3.12-slim AS runtime

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
USER app
EXPOSE 8000

# Liveness only: /ready decides traffic, /health decides restarts.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
