.PHONY: install lock lock-check dev test lint fmt migrate migration

install:
	uv sync

lock:
	uv lock

lock-check:
	uv lock --check

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy app

fmt:
	uv run ruff format .
	uv run ruff check --fix .

migrate:
	uv run alembic upgrade head

migration:
	@test -n "$(m)" || (echo "usage: make migration m='describe change'" && exit 1)
	uv run alembic revision --autogenerate -m "$(m)"
