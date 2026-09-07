"""Prompt versioning — PUT /prompts/active flips previous is_active, inserts new active row."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.prompt import Prompt


def _count(session_factory, **filters) -> int:
    with session_factory() as session:
        stmt = select(func.count()).select_from(Prompt)
        for field, value in filters.items():
            stmt = stmt.where(getattr(Prompt, field) == value)
        return session.execute(stmt).scalar_one()


def test_active_endpoint_returns_bootstrapped_prompt(authed: TestClient) -> None:
    response = authed.get("/api/v1/prompts/active")
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is True
    assert "{domain}" in body["text"]
    assert body["missing_placeholders"] == []


def test_put_flips_previous_active_and_inserts_new(
    authed: TestClient, session_factory
) -> None:
    original = authed.get("/api/v1/prompts/active").json()
    assert _count(session_factory, is_active=True) == 1

    replacement = "New prompt: {domain} {last_name} {gender} {template}"
    response = authed.put("/api/v1/prompts/active", json={"text": replacement})
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is True
    assert body["text"] == replacement
    assert body["id"] != original["id"]

    # Exactly one active row at any time (partial unique index invariant).
    assert _count(session_factory, is_active=True) == 1
    # And the old row is now inactive but still present.
    with session_factory() as session:
        previous = session.get(Prompt, original["id"])
        assert previous is not None
        assert previous.is_active is False


def test_history_returns_recent_versions_newest_first(
    authed: TestClient,
) -> None:
    for i in range(3):
        authed.put(
            "/api/v1/prompts/active",
            json={"text": f"version {i}: {{domain}} {{last_name}} {{gender}} {{template}}"},
        )

    history = authed.get("/api/v1/prompts/history").json()
    # Bootstrap + 3 updates = 4 entries in history.
    assert len(history) == 4
    # Newest first.
    assert history[0]["text"].startswith("version 2")
    # Exactly the newest is active.
    active_count = sum(1 for p in history if p["is_active"])
    assert active_count == 1
    assert history[0]["is_active"] is True


def test_placeholder_lint_flags_incomplete_prompt(authed: TestClient) -> None:
    response = authed.put(
        "/api/v1/prompts/active",
        json={"text": "Only {domain} — nothing else"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["missing_placeholders"] == ["last_name", "gender", "template"]
