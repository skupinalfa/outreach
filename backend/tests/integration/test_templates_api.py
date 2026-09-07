"""Templates CRUD + archive-on-referenced-delete."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations import openai_client
from app.models.template import Template


def test_list_default_hides_archived(authed: TestClient, session_factory) -> None:
    with session_factory() as session:
        session.add(Template(name="Archived", body="only {domain}", is_archived=True))
        session.commit()

    body = authed.get("/api/v1/templates").json()
    names = [t["name"] for t in body]
    assert "Archived" not in names
    # The bootstrap seeds one "Default" template.
    assert "Default" in names


def test_include_archived_returns_all(authed: TestClient, session_factory) -> None:
    with session_factory() as session:
        session.add(Template(name="Archived", body="only {domain}", is_archived=True))
        session.commit()

    body = authed.get(
        "/api/v1/templates", params={"include_archived": "true"}
    ).json()
    names = [t["name"] for t in body]
    assert "Archived" in names


def test_create_reports_missing_placeholders(authed: TestClient) -> None:
    response = authed.post(
        "/api/v1/templates",
        json={"name": "Sparse", "body": "Just some prose about {domain}."},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["missing_placeholders"] == ["last_name", "gender", "template"]


def test_duplicate_active_name_conflicts(authed: TestClient) -> None:
    authed.post("/api/v1/templates", json={"name": "Follow up", "body": "{domain}"})
    dup = authed.post("/api/v1/templates", json={"name": "follow up", "body": "{domain}"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"


def test_patch_body_updates_missing_placeholders(authed: TestClient) -> None:
    created = authed.post(
        "/api/v1/templates", json={"name": "X", "body": "{domain} {last_name} {gender} {template}"}
    ).json()
    assert created["missing_placeholders"] == []

    patched = authed.patch(
        f"/api/v1/templates/{created['id']}",
        json={"body": "only {domain}"},
    ).json()
    assert patched["missing_placeholders"] == ["last_name", "gender", "template"]


def test_delete_hard_when_unreferenced(authed: TestClient) -> None:
    created = authed.post(
        "/api/v1/templates", json={"name": "Disposable", "body": "{domain}"}
    ).json()
    response = authed.delete(f"/api/v1/templates/{created['id']}")
    assert response.status_code == 204
    assert authed.get(f"/api/v1/templates/{created['id']}").status_code == 404


def test_delete_archives_when_referenced_by_draft(
    authed: TestClient,
    session_factory,
    monkeypatch,
) -> None:
    from app.models.contact import ContactStatus  # local import to avoid top-level noise
    from app.models.settings import Settings as SettingsRow
    from app.security import secrets as secret_helpers

    # Seed OpenAI key so /drafts can run.
    with session_factory() as session:
        session.get(SettingsRow, 1).openai_api_key_ct = secret_helpers.encrypt("k")
        session.commit()

    monkeypatch.setattr(
        openai_client,
        "generate",
        lambda prompt, api_key, model="", max_tokens=0: '{"subject":"S","text":"B"}',
    )

    template = authed.post(
        "/api/v1/templates", json={"name": "Referenced", "body": "{domain} {last_name} {gender} {template}"}
    ).json()
    org = authed.post(
        "/api/v1/organisations", json={"name": "Acme", "domain": "acme.com"}
    ).json()
    contact = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org["id"],
            "first_name": "A",
            "last_name": "B",
            "email": "a@acme.com",
        },
    ).json()
    # Move contact to ENRICHED so generation is allowed.
    with session_factory() as session:
        from app.models.contact import Contact

        session.get(Contact, contact["id"]).status = ContactStatus.ENRICHED
        session.commit()

    draft_response = authed.post(
        f"/api/v1/contacts/{contact['id']}/drafts",
        json={"template_id": template["id"]},
    )
    assert draft_response.status_code == 201, draft_response.text

    delete = authed.delete(f"/api/v1/templates/{template['id']}")
    assert delete.status_code == 204

    fetched = authed.get(f"/api/v1/templates/{template['id']}").json()
    assert fetched["is_archived"] is True

    # It also drops out of the default list but remains in include_archived.
    default_list = [t["id"] for t in authed.get("/api/v1/templates").json()]
    assert template["id"] not in default_list
    all_list = [
        t["id"]
        for t in authed.get("/api/v1/templates", params={"include_archived": "true"}).json()
    ]
    assert template["id"] in all_list

    # Sanity: the row really still exists in the DB.
    with session_factory() as session:
        assert (
            session.execute(select(Template).where(Template.id == template["id"])).scalar_one()
            is not None
        )
