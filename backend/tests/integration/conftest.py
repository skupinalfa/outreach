"""Per-test-session Postgres 16 container. Each test function gets a clean transaction rolled
back on exit so tests don't leak state."""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        raw = pg.get_connection_url()
        # Normalise whatever prefix testcontainers picks (psycopg2, psycopg, plain) to psycopg v3.
        for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
            if raw.startswith(prefix):
                url = "postgresql+psycopg://" + raw[len(prefix) :]
                break
        else:
            url = raw
        os.environ["DATABASE_URL"] = url
        yield url


@pytest.fixture(scope="session")
def _engine(postgres_url: str):
    from alembic import command
    from alembic.config import Config

    engine = create_engine(postgres_url, future=True)

    # Run all migrations against the fresh DB.
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_cfg = Config(os.path.join(root, "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    alembic_cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture
def db(_engine) -> Iterator[Session]:
    connection = _engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


_ALL_TABLES = (
    "todo",
    "sent_message",
    "draft",
    "contact",
    "prompt",
    "template",
    "session",
    "settings",
    "organisation",
)


@pytest.fixture
def session_factory(_engine):
    """Truncate all tables between tests + session factory tests can borrow to seed data."""
    from app import bootstrap as boot
    from app import db as db_module
    from app.models.settings import Settings as SettingsRow
    from app.security import auth as auth_service

    with _engine.begin() as conn:
        conn.exec_driver_sql(
            "TRUNCATE " + ", ".join(_ALL_TABLES) + " RESTART IDENTITY CASCADE"
        )

    factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)

    # The app was imported before the testcontainer existed, so `app.db.SessionLocal`
    # points at a stale URL. Redirect it here so the FastAPI lifespan (which calls
    # `SessionLocal()` during bootstrap) uses the same DB as the tests.
    db_module.engine = _engine
    db_module.SessionLocal = factory

    with factory() as session:
        boot.bootstrap_all(session)
        settings_row = session.get(SettingsRow, 1)
        assert settings_row is not None
        settings_row.master_password_hash = auth_service.hash_password("integration-password")
        session.commit()

    return factory


@pytest.fixture
def app_client(session_factory) -> Iterator[TestClient]:
    """FastAPI TestClient sharing the same engine as `session_factory`."""
    from app.db import get_db
    from app.main import create_app

    app = create_app()

    def _override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def authed(app_client: TestClient) -> TestClient:
    """A TestClient with a live session cookie for the seeded master password."""
    response = app_client.post("/api/v1/auth/login", json={"password": "integration-password"})
    assert response.status_code in (200, 204), response.text
    return app_client
