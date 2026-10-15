FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv==0.5.11

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY . .

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000
# `sh -c` so we can chain migrations before the server AND interpolate $PORT
# (Railway injects PORT at runtime; local docker-compose leaves it unset and
# falls back to 8000). `exec` replaces the shell with uvicorn so PID 1 is the
# server itself — SIGTERM propagation and graceful shutdown work correctly.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
