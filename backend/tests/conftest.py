"""Shared pytest fixtures.

Integration tests get a real Postgres container from `tests/integration/conftest.py`; unit and
contract tests do not touch the database.
"""
from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    os.environ.setdefault("FERNET_KEY", "3lQx9lVXKmvB3-pJ0PDPClZgZjsMTQZjq2f0M7bqE0Y=")  # test-only
    os.environ.setdefault("SESSION_SECRET", "test-session-secret-please-do-not-use-in-prod")
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+psycopg://coldmail:coldmail@localhost:5432/coldmail_test"
    )
    os.environ.setdefault("COOKIE_SECURE", "false")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("LIVE_INTEGRATION") == "1":
        return
    skip_live = pytest.mark.skip(reason="LIVE_INTEGRATION=1 required to run live-network tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
