"""Integration test for POST /contacts/{id}/drafts.

Stubs the OpenAI boundary so the test is hermetic. Contract-level OpenAI shape is exercised
separately by `tests/contract/test_openai.py` via vcrpy.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations import openai_client
from app.models.settings import Settings as SettingsRow
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType
from app.security import secrets as secret_helpers


def _seed_openai_key_and_get_template(session_factory) -> int:
    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        row.openai_api_key_ct = secret_helpers.encrypt("test-openai-key")
        template_id = session.execute(select(Template).limit(1)).scalar_one().id
        session.commit()
    return template_id


def _make_enriched_lead(authed: TestClient) -> int:
    org = authed.post(
        "/api/v1/organisations",
        json={"name": "Stripe", "domain": "stripe.com"},
    ).json()
    contact = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org["id"],
            "first_name": "Patrick",
            "last_name": "Collison",
            "gender": "m",
            "email": "patrick@stripe.com",
        },
    ).json()
    return contact["id"]


def test_generate_draft_creates_send_todo_and_persists_snapshots(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_id = _seed_openai_key_and_get_template(session_factory)
    contact_id = _make_enriched_lead(authed)

    monkeypatch.setattr(
        openai_client,
        "generate",
        lambda prompt, api_key, model="", max_tokens=0: (
            '{"subject": "Hallo Herr Collison", "text": "Guten Tag, ..."}'
        ),
    )

    response = authed.post(
        f"/api/v1/contacts/{contact_id}/drafts",
        json={"template_id": template_id},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["subject"] == "Hallo Herr Collison"
    assert body["body"].startswith("Guten Tag")
    assert body["template_id"] == template_id

    with session_factory() as session:
        todo = session.execute(
            select(Todo).where(
                Todo.contact_id == contact_id,
                Todo.type == TodoType.SEND,
            )
        ).scalar_one()
        assert todo.status == TodoStatus.OPEN
        assert todo.draft_id == body["id"]
        assert "Collison" in todo.title


def test_generate_draft_persists_failure_audit(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_id = _seed_openai_key_and_get_template(session_factory)
    contact_id = _make_enriched_lead(authed)

    def _boom(*_args, **_kwargs):
        raise openai_client.OpenAIError("upstream 500 after retries")

    monkeypatch.setattr(openai_client, "generate", _boom)

    response = authed.post(
        f"/api/v1/contacts/{contact_id}/drafts",
        json={"template_id": template_id},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openai_error"

    fetched = authed.get(f"/api/v1/contacts/{contact_id}").json()
    assert fetched["last_generated_at"] is not None
    assert fetched["last_generation_error"] is not None
    assert "500" in fetched["last_generation_error"]


def test_generate_draft_requires_openai_key(authed: TestClient, session_factory) -> None:
    contact_id = _make_enriched_lead(authed)
    with session_factory() as session:
        template_id = session.execute(select(Template).limit(1)).scalar_one().id

    response = authed.post(
        f"/api/v1/contacts/{contact_id}/drafts",
        json={"template_id": template_id},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"
