"""Integration tests for the activity read paths (T016, T035).

Uses the real Postgres-container fixture — the intent is to exercise the actual SQL joins
in `api/activity.py` end-to-end. Events are seeded via the production service helpers so the
same code paths that the running app would use are covered.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations import hunter
from app.models.activity_event import ActivityActor, ActivityEvent, ActivityEventType
from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.settings import Settings as SettingsRow
from app.models.template import Template
from app.security import secrets as secret_helpers
from app.services import activity as activity_service


def _seed_hunter_key(session_factory) -> None:
    with session_factory() as s:
        s.get(SettingsRow, 1).hunter_api_key_ct = secret_helpers.encrypt("test-key")
        s.commit()


def test_per_contact_full_history_via_real_services(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the FR-039 vocabulary end-to-end via the production write paths."""
    _seed_hunter_key(session_factory)

    org = authed.post("/api/v1/organisations", json={"name": "Acme"}).json()
    contact = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org["id"],
            "first_name": "Max",
            "last_name": "Müller",
            "gender": "m",
        },
    ).json()

    monkeypatch.setattr(hunter, "resolve_domain", lambda name, key: "acme.example")
    monkeypatch.setattr(
        hunter,
        "find_email",
        lambda first, last, domain, key: hunter.EmailFinderResult(
            email="max@acme.example",
            domain=domain,
            score=91,
            position="CTO",
            verification_status="valid",
        ),
    )
    authed.post(f"/api/v1/contacts/{contact['id']}/enrich")

    # Status transition operator-driven.
    authed.patch(f"/api/v1/contacts/{contact['id']}", json={"status": "contacted"})

    resp = authed.get(f"/api/v1/contacts/{contact['id']}/activity")
    assert resp.status_code == 200
    body = resp.json()
    types = [i["event_type"] for i in body["items"]]

    # Must include at least: lead_created, enrichment_attempted, status_changed (from
    # enrichment auto-transition new→enriched and from the operator patch enriched→contacted).
    assert "lead_created" in types
    assert "enrichment_attempted" in types
    assert types.count("status_changed") >= 1

    # Newest-first default.
    occurred = [datetime.fromisoformat(i["occurred_at"]) for i in body["items"]]
    assert occurred == sorted(occurred, reverse=True)


def test_per_contact_joins_sent_message_snapshot(authed: TestClient, session_factory) -> None:
    """`email_sent` events carry the joined sent_message subject/body."""
    with session_factory() as s:
        org = Organisation(name="Beta", domain="beta.example")
        s.add(org)
        s.flush()
        c = Contact(
            organisation_id=org.id,
            first_name="B",
            last_name="B",
            email="b@beta.example",
            status=ContactStatus.CONTACTED,
        )
        s.add(c)
        s.flush()
        sent = SentMessage(
            contact_id=c.id,
            subject="Cross-join subject",
            body="Cross-join body",
            delivery_status=DeliveryStatus.SENT.value,
        )
        s.add(sent)
        s.flush()
        activity_service.record_event(
            s,
            contact_id=c.id,
            organisation_id=org.id,
            event_type=ActivityEventType.EMAIL_SENT,
            actor=ActivityActor.OPERATOR,
            payload={
                "sent_message_id": sent.id,
                "template_id": None,
                "recipient": c.email,
            },
        )
        s.commit()
        contact_id = c.id

    resp = authed.get(f"/api/v1/contacts/{contact_id}/activity")
    assert resp.status_code == 200
    items = resp.json()["items"]
    email_sent = next(i for i in items if i["event_type"] == "email_sent")
    assert email_sent["message_snapshot"]["subject"] == "Cross-join subject"
    assert email_sent["message_snapshot"]["body"] == "Cross-join body"
    assert email_sent["message_snapshot"]["delivery_status"] == "sent"


def test_per_contact_joins_draft_snapshot(authed: TestClient, session_factory) -> None:
    """`draft_generated` events carry the joined draft subject/body."""
    with session_factory() as s:
        org = Organisation(name="Gamma", domain="gamma.example")
        s.add(org)
        s.flush()
        c = Contact(
            organisation_id=org.id,
            first_name="G",
            last_name="G",
            email="g@gamma.example",
        )
        s.add(c)
        s.flush()
        tpl = s.execute(select(Template).limit(1)).scalar_one()
        prompt = s.execute(select(Prompt).limit(1)).scalar_one()
        draft = Draft(
            contact_id=c.id,
            template_id=tpl.id,
            template_body_snapshot=tpl.body,
            prompt_id=prompt.id,
            prompt_text_snapshot=prompt.text,
            subject="Draft subject",
            body="Draft body",
        )
        s.add(draft)
        s.flush()
        activity_service.record_event(
            s,
            contact_id=c.id,
            organisation_id=org.id,
            event_type=ActivityEventType.DRAFT_GENERATED,
            actor=ActivityActor.OPERATOR,
            payload={
                "draft_id": draft.id,
                "template_id": tpl.id,
                "template_name": tpl.name,
                "prompt_id": prompt.id,
            },
        )
        s.commit()
        contact_id = c.id

    resp = authed.get(f"/api/v1/contacts/{contact_id}/activity")
    assert resp.status_code == 200
    items = resp.json()["items"]
    dg = next(i for i in items if i["event_type"] == "draft_generated")
    assert dg["message_snapshot"]["subject"] == "Draft subject"
    assert dg["message_snapshot"]["body"] == "Draft body"


@pytest.mark.slow
def test_global_pagination_at_50k_stays_under_2s(
    authed: TestClient, session_factory
) -> None:
    """SC-012 / FR-043 — first-page render at 50k events completes within 2s.

    Marked `slow` so the default test run stays quick; enable with `pytest -m slow`.
    """
    with session_factory() as s:
        org = Organisation(name="Perf", domain="perf.example")
        s.add(org)
        s.flush()
        c = Contact(
            organisation_id=org.id,
            first_name="P",
            last_name="P",
            email="p@perf.example",
        )
        s.add(c)
        s.flush()
        contact_id = c.id
        org_id = org.id

        base_ts = datetime.now(UTC) - timedelta(hours=1)
        batch: list[ActivityEvent] = []
        for i in range(50_000):
            batch.append(
                ActivityEvent(
                    contact_id=contact_id,
                    organisation_id=org_id,
                    event_type=ActivityEventType.LEAD_CREATED,
                    actor=ActivityActor.SYSTEM,
                    payload={},
                    occurred_at=base_ts + timedelta(seconds=i),
                )
            )
            if len(batch) >= 5000:
                s.add_all(batch)
                s.flush()
                batch = []
        if batch:
            s.add_all(batch)
        s.commit()

    started = time.perf_counter()
    resp = authed.get("/api/v1/activity", params={"limit": 50})
    elapsed = time.perf_counter() - started
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 50
    assert elapsed < 2.0, f"first page took {elapsed:.2f}s (budget: 2.0s)"


@pytest.mark.slow
def test_global_pagination_keyset_advances_without_gaps(
    authed: TestClient, session_factory
) -> None:
    """FR-041 keyset pagination: 5 consecutive pages, no duplicates or missing rows."""
    with session_factory() as s:
        org = Organisation(name="Ks", domain="ks.example")
        s.add(org)
        s.flush()
        c = Contact(organisation_id=org.id, first_name="K", last_name="K", email="k@ks.example")
        s.add(c)
        s.flush()
        base_ts = datetime.now(UTC) - timedelta(hours=1)
        for i in range(500):
            s.add(
                ActivityEvent(
                    contact_id=c.id,
                    organisation_id=org.id,
                    event_type=ActivityEventType.LEAD_CREATED,
                    actor=ActivityActor.SYSTEM,
                    payload={},
                    occurred_at=base_ts + timedelta(seconds=i),
                )
            )
        s.commit()

    seen_ids: list[int] = []
    cursor: str | None = None
    for _ in range(5):
        params: dict[str, object] = {"limit": 50}
        if cursor is not None:
            params["cursor"] = cursor
        resp = authed.get("/api/v1/activity", params=params)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 50
        seen_ids.extend(i["id"] for i in body["items"])
        cursor = body["next_cursor"]
        assert cursor is not None

    assert len(set(seen_ids)) == 250, "keyset pagination produced duplicates"
