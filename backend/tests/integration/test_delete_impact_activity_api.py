"""Contract test — DeleteImpact counts include activity_events (T042, FR-052)."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.activity_event import ActivityActor, ActivityEvent, ActivityEventType
from app.models.contact import Contact
from app.models.organisation import Organisation
from app.services import activity as activity_service


def _seed(session_factory) -> tuple[int, int, int]:
    with session_factory() as s:
        org = Organisation(name="ImpactOrg", domain="impact.example")
        s.add(org)
        s.flush()
        c = Contact(
            organisation_id=org.id,
            first_name="I",
            last_name="I",
            email="i@impact.example",
        )
        s.add(c)
        s.flush()
        for _ in range(4):
            activity_service.record_event(
                s,
                contact_id=c.id,
                organisation_id=org.id,
                event_type=ActivityEventType.LEAD_CREATED,
                actor=ActivityActor.OPERATOR,
            )
        s.commit()
        return org.id, c.id, 4


def test_contact_delete_impact_includes_activity_count(
    authed: TestClient, session_factory
) -> None:
    _org_id, contact_id, expected = _seed(session_factory)
    resp = authed.get(f"/api/v1/contacts/{contact_id}/delete-impact")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["activity_events"] == expected

    # Direct-count matches (no cache, per FR-052).
    with session_factory() as s:
        direct = s.execute(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.contact_id == contact_id
            )
        ).scalar_one()
        assert direct == expected


def test_organisation_delete_impact_includes_activity_count(
    authed: TestClient, session_factory
) -> None:
    org_id, _contact_id, expected = _seed(session_factory)
    resp = authed.get(f"/api/v1/organisations/{org_id}/delete-impact")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["activity_events"] == expected

    with session_factory() as s:
        direct = s.execute(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.organisation_id == org_id
            )
        ).scalar_one()
        assert direct == expected
