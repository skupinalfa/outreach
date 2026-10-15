"""API contract tests for the activity endpoints (T015, T034).

Both routes return `ActivityEventView`; message-carrying events (`email_sent`,
`draft_generated`, `draft_regenerated`, `draft_stored_in_mailbox`) carry a `message_snapshot`
joined at read time from `sent_message` / `draft` (data-model.md § Illustrative queries).
Per-contact route supports `?order=asc|desc` toggle; global route accepts multi-value
`event_type`, `contact_id`, `organisation_id`, `since`/`until`, `window`, `cursor`, `limit`.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.activity_event import ActivityActor, ActivityEvent, ActivityEventType
from app.models.contact import Contact
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.template import Template


def _seed_contact_with_history(session_factory) -> tuple[int, int, int]:
    """Seed one contact with a draft + sent message + a spread of activity events."""
    with session_factory() as s:
        org = Organisation(name="Acme GmbH", domain="acme.example")
        s.add(org)
        s.flush()
        contact = Contact(
            organisation_id=org.id,
            first_name="Max",
            last_name="Müller",
            email="max@acme.example",
        )
        s.add(contact)
        s.flush()

        tpl = s.execute(select(Template).limit(1)).scalar_one()
        prompt = s.execute(select(Prompt).limit(1)).scalar_one()
        draft = Draft(
            contact_id=contact.id,
            template_id=tpl.id,
            template_body_snapshot=tpl.body,
            prompt_id=prompt.id,
            prompt_text_snapshot=prompt.text,
            subject="Kurz zu Acme",
            body="Guten Tag Herr Müller,\n\nBody text.",
        )
        s.add(draft)
        s.flush()

        sent = SentMessage(
            contact_id=contact.id,
            subject="Kurz zu Acme",
            body="Guten Tag Herr Müller,\n\nSent body text.",
            delivery_status=DeliveryStatus.SENT.value,
        )
        s.add(sent)
        s.flush()

        base_ts = datetime.now(UTC) - timedelta(minutes=10)
        events = [
            ActivityEvent(
                contact_id=contact.id,
                organisation_id=org.id,
                event_type=ActivityEventType.LEAD_CREATED,
                actor=ActivityActor.OPERATOR,
                payload={},
                occurred_at=base_ts,
            ),
            ActivityEvent(
                contact_id=contact.id,
                organisation_id=org.id,
                event_type=ActivityEventType.ENRICHMENT_ATTEMPTED,
                actor=ActivityActor.OPERATOR,
                payload={"outcome": "email_found", "reason": None, "hunter_confidence": 92},
                occurred_at=base_ts + timedelta(minutes=1),
            ),
            ActivityEvent(
                contact_id=contact.id,
                organisation_id=org.id,
                event_type=ActivityEventType.DRAFT_GENERATED,
                actor=ActivityActor.OPERATOR,
                payload={
                    "draft_id": draft.id,
                    "template_id": tpl.id,
                    "template_name": tpl.name,
                    "prompt_id": prompt.id,
                },
                occurred_at=base_ts + timedelta(minutes=2),
            ),
            ActivityEvent(
                contact_id=contact.id,
                organisation_id=org.id,
                event_type=ActivityEventType.EMAIL_SENT,
                actor=ActivityActor.OPERATOR,
                payload={
                    "sent_message_id": sent.id,
                    "template_id": tpl.id,
                    "recipient": contact.email,
                },
                occurred_at=base_ts + timedelta(minutes=3),
            ),
            ActivityEvent(
                contact_id=contact.id,
                organisation_id=org.id,
                event_type=ActivityEventType.STATUS_CHANGED,
                actor=ActivityActor.SYSTEM,
                payload={"from": "enriched", "to": "contacted"},
                occurred_at=base_ts + timedelta(minutes=4),
            ),
        ]
        s.add_all(events)
        s.commit()
        return contact.id, org.id, sent.id


def test_per_contact_returns_activity_view_shape(authed: TestClient, session_factory) -> None:
    contact_id, org_id, sent_id = _seed_contact_with_history(session_factory)

    resp = authed.get(f"/api/v1/contacts/{contact_id}/activity")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert set(body.keys()) == {"items", "total", "contact"}
    assert body["total"] == 5
    assert body["contact"]["id"] == contact_id
    assert body["contact"]["organisation"]["id"] == org_id

    # Default order is newest-first.
    types = [item["event_type"] for item in body["items"]]
    assert types[0] == "status_changed"
    assert types[-1] == "lead_created"

    # Every item has the full ActivityEventView shape.
    for item in body["items"]:
        assert set(item.keys()) >= {
            "id",
            "event_type",
            "actor",
            "occurred_at",
            "contact",
            "organisation",
            "summary",
            "payload",
            "message_snapshot",
        }
        assert item["contact"]["id"] == contact_id
        assert item["organisation"]["id"] == org_id

    # Message-carrying events carry a snapshot; others don't.
    for item in body["items"]:
        if item["event_type"] in {
            "email_sent",
            "draft_generated",
            "draft_regenerated",
            "draft_stored_in_mailbox",
        }:
            assert item["message_snapshot"] is not None
        else:
            assert item["message_snapshot"] is None

    email_sent = next(i for i in body["items"] if i["event_type"] == "email_sent")
    assert email_sent["message_snapshot"]["subject"] == "Kurz zu Acme"
    assert email_sent["message_snapshot"]["delivery_status"] == "sent"
    assert email_sent["payload"]["sent_message_id"] == sent_id


def test_per_contact_order_asc_toggle(authed: TestClient, session_factory) -> None:
    contact_id, _org_id, _sent_id = _seed_contact_with_history(session_factory)

    resp = authed.get(f"/api/v1/contacts/{contact_id}/activity", params={"order": "asc"})
    assert resp.status_code == 200
    types = [item["event_type"] for item in resp.json()["items"]]
    assert types[0] == "lead_created"
    assert types[-1] == "status_changed"


def test_per_contact_404_when_contact_missing(authed: TestClient, session_factory) -> None:
    _seed_contact_with_history(session_factory)
    resp = authed.get("/api/v1/contacts/999999/activity")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_global_activity_filters_and_cursor(authed: TestClient, session_factory) -> None:
    contact_id, org_id, _sent_id = _seed_contact_with_history(session_factory)

    # Unfiltered — returns all 5 events.
    resp = authed.get("/api/v1/activity")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"items", "next_cursor", "has_more"}
    assert len(body["items"]) == 5
    assert body["has_more"] is False
    assert body["next_cursor"] is None

    # Event-type filter — only email_sent.
    resp = authed.get("/api/v1/activity", params={"event_type": "email_sent"})
    assert resp.status_code == 200
    body = resp.json()
    assert [i["event_type"] for i in body["items"]] == ["email_sent"]

    # Multi-value event_type.
    resp = authed.get(
        "/api/v1/activity",
        params=[("event_type", "email_sent"), ("event_type", "draft_generated")],
    )
    assert resp.status_code == 200
    types = {i["event_type"] for i in resp.json()["items"]}
    assert types == {"email_sent", "draft_generated"}

    # Contact filter.
    resp = authed.get("/api/v1/activity", params={"contact_id": contact_id})
    assert resp.status_code == 200
    assert all(i["contact"]["id"] == contact_id for i in resp.json()["items"])

    # Organisation filter.
    resp = authed.get("/api/v1/activity", params={"organisation_id": org_id})
    assert resp.status_code == 200
    assert all(i["organisation"]["id"] == org_id for i in resp.json()["items"])


def test_global_activity_pagination_via_cursor(authed: TestClient, session_factory) -> None:
    _seed_contact_with_history(session_factory)

    resp = authed.get("/api/v1/activity", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["has_more"] is True
    assert body["next_cursor"]

    resp2 = authed.get("/api/v1/activity", params={"limit": 2, "cursor": body["next_cursor"]})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["items"]) == 2

    # No overlap.
    first_ids = {i["id"] for i in body["items"]}
    second_ids = {i["id"] for i in body2["items"]}
    assert first_ids.isdisjoint(second_ids)

    resp3 = authed.get("/api/v1/activity", params={"limit": 2, "cursor": body2["next_cursor"]})
    body3 = resp3.json()
    assert len(body3["items"]) == 1
    assert body3["has_more"] is False


def test_global_activity_rejects_bad_cursor(authed: TestClient, session_factory) -> None:
    _seed_contact_with_history(session_factory)
    resp = authed.get("/api/v1/activity", params={"cursor": "not-a-valid-cursor"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_global_activity_window_preset(authed: TestClient, session_factory) -> None:
    _seed_contact_with_history(session_factory)

    resp = authed.get("/api/v1/activity", params={"window": "last_7d"})
    assert resp.status_code == 200
    # The seed data is all recent — every event fits inside last_7d.
    assert len(resp.json()["items"]) == 5

    resp = authed.get("/api/v1/activity", params={"window": "today"})
    assert resp.status_code == 200
    # Same — all events are within the last 10 minutes.
    assert len(resp.json()["items"]) == 5
