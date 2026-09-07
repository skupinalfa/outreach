"""GET /api/v1/contacts/{id}/delete-impact — powers the FR-027a confirmation dialog."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType


def test_delete_impact_counts_contact_subtree(authed: TestClient, session_factory) -> None:
    """Fixture: 1 draft, 3 sent messages, 2 open + 1 scheduled = 3 open_todos,
    1 done todo that must not count."""
    with session_factory() as session:
        template = session.execute(select(Template).limit(1)).scalar_one()
        prompt = session.execute(select(Prompt).limit(1)).scalar_one()

        org = Organisation(name="Acme")
        session.add(org)
        session.flush()
        contact = Contact(
            organisation_id=org.id,
            first_name="Max",
            last_name="Müller",
            email="max@acme.de",
            status=ContactStatus.CONTACTED,
        )
        session.add(contact)
        session.flush()

        session.add(
            Draft(
                contact_id=contact.id,
                template_id=template.id,
                template_body_snapshot=template.body,
                prompt_id=prompt.id,
                prompt_text_snapshot=prompt.text,
                subject="s",
                body="b",
            )
        )
        for _ in range(3):
            session.add(
                SentMessage(
                    contact_id=contact.id,
                    subject="s",
                    body="b",
                    delivery_status=DeliveryStatus.SENT.value,
                )
            )

        now = datetime.now(UTC)
        for i in range(2):
            session.add(
                Todo(
                    type=TodoType.SEND,
                    title=f"open-{i}",
                    contact_id=contact.id,
                    due_at=now,
                    status=TodoStatus.OPEN,
                )
            )
        session.add(
            Todo(
                type=TodoType.FOLLOW_UP,
                title="sched",
                contact_id=contact.id,
                due_at=now + timedelta(days=5),
                status=TodoStatus.SCHEDULED,
            )
        )
        session.add(
            Todo(
                type=TodoType.SEND,
                title="done",
                contact_id=contact.id,
                due_at=now - timedelta(days=1),
                status=TodoStatus.DONE,
                completed_at=now - timedelta(days=1),
            )
        )
        session.commit()
        contact_id = contact.id

    body = authed.get(f"/api/v1/contacts/{contact_id}/delete-impact").json()
    assert body["target"] == {"kind": "contact", "id": contact_id, "name": "Max Müller"}
    assert body["counts"] == {
        "contacts": 0,
        "drafts": 1,
        "sent_messages": 3,
        "open_todos": 3,
    }


def test_delete_impact_bare_contact_is_all_zeros(authed: TestClient) -> None:
    org = authed.post("/api/v1/organisations", json={"name": "Acme"}).json()
    contact = authed.post(
        "/api/v1/contacts",
        json={"organisation_id": org["id"], "first_name": "A", "last_name": "B"},
    ).json()
    body = authed.get(f"/api/v1/contacts/{contact['id']}/delete-impact").json()
    assert body["target"]["kind"] == "contact"
    assert body["target"]["name"] == "A B"
    assert body["counts"] == {
        "contacts": 0,
        "drafts": 0,
        "sent_messages": 0,
        "open_todos": 0,
    }


def test_delete_impact_unknown_contact_returns_404(authed: TestClient) -> None:
    response = authed.get("/api/v1/contacts/999999/delete-impact")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
