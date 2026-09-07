"""FR-037 + SC-010: Dashboard metrics recompute live after a cascade delete.

Deleted rows must disappear from every window (last 7d, last 30d, funnel) — no
lingering counter caches, no soft-delete ghosts.
"""
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


def _seed_org_with_activity(session_factory) -> int:
    """Seed one organisation whose contacts contribute to every 7d + 30d metric."""
    with session_factory() as session:
        template = session.execute(select(Template).limit(1)).scalar_one()
        prompt = session.execute(select(Prompt).limit(1)).scalar_one()

        org = Organisation(name="PurgeMe")
        session.add(org)
        session.flush()

        contacts: list[Contact] = []
        for i in range(2):
            c = Contact(
                organisation_id=org.id,
                first_name=f"F{i}",
                last_name=f"L{i}",
                email=f"c{i}@purgeme.co",
                status=ContactStatus.CONTACTED,
            )
            session.add(c)
            contacts.append(c)
        session.flush()

        # 1 draft, 2 sent messages today (last 7d + last 30d), 1 reply.
        session.add(
            Draft(
                contact_id=contacts[0].id,
                template_id=template.id,
                template_body_snapshot=template.body,
                prompt_id=prompt.id,
                prompt_text_snapshot=prompt.text,
                subject="s",
                body="b",
            )
        )
        for _ in range(2):
            session.add(
                SentMessage(
                    contact_id=contacts[0].id,
                    subject="s",
                    body="b",
                    delivery_status=DeliveryStatus.SENT.value,
                )
            )
        contacts[1].status = ContactStatus.REPLIED

        # 1 more sent 20 days ago — inside 30d window, outside 7d window.
        old_sent = SentMessage(
            contact_id=contacts[0].id,
            subject="old",
            body="b",
            delivery_status=DeliveryStatus.SENT.value,
        )
        session.add(old_sent)
        session.flush()
        old_sent.sent_at = datetime.now(UTC) - timedelta(days=20)

        session.commit()
        return org.id


def _snapshot(authed: TestClient) -> dict:
    return authed.get("/api/v1/dashboard/overview").json()


def test_dashboard_metrics_drop_after_org_cascade_delete(
    authed: TestClient, session_factory
) -> None:
    org_id = _seed_org_with_activity(session_factory)

    before = _snapshot(authed)
    assert before["onboarding_required"] is False
    assert before["activity"]["leads_added"] == 2
    assert before["activity"]["drafts_generated"] == 1
    assert before["activity"]["emails_sent"] == 2
    assert before["activity"]["replies_logged"] == 1
    assert before["activity_30d"]["emails_sent"] == 3
    assert before["funnel_30d"]["sent"] == 3
    assert before["funnel_30d"]["replied"] == 1

    response = authed.delete(f"/api/v1/organisations/{org_id}")
    assert response.status_code == 204

    after = _snapshot(authed)
    # With every seeded row cascade-removed, the dashboard falls back to the onboarding
    # shape (no contacts left → FR-035 onboarding state).
    assert after == {"onboarding_required": True}
