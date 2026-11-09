"""Behavioural tenant-isolation tests for the repository layer (S2-A2).

Skipped unless ``AIOPS_TEST_DATABASE_URL`` points at a throwaway PostgreSQL
(see ``tests/integration/conftest.py``). The static guard in
``tests/unit/test_tenant_isolation_lint.py`` catches an omitted filter; these
tests prove the filter actually holds across tenants.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from aiops.central.db import repositories as repo
from aiops.central.db.models import AuditEvent, Incident, IncidentLink, IncidentStateHistory


def _tenant_and_site(connection: Connection) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, site_id = uuid.uuid4(), uuid.uuid4()
    connection.execute(
        text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
        {"id": tenant_id, "name": f"tenant-{tenant_id}"},
    )
    connection.execute(
        text("INSERT INTO sites (id, tenant_id, name) VALUES (:id, :tenant, :name)"),
        {"id": site_id, "tenant": tenant_id, "name": f"site-{site_id}"},
    )
    return tenant_id, site_id


def test_incident_queries_are_tenant_scoped(db: Engine) -> None:
    with db.begin() as connection:
        tenant_a, _ = _tenant_and_site(connection)
        tenant_b, _ = _tenant_and_site(connection)

    with Session(db) as session:
        incident_a = repo.create_incident(
            session, tenant_id=tenant_a, fingerprint="fp-a", severity="warning"
        )
        incident_b = repo.create_incident(
            session, tenant_id=tenant_b, fingerprint="fp-b", severity="error"
        )
        session.commit()

        assert repo.get_incident(session, tenant_id=tenant_a, incident_id=incident_a.id) is not None
        assert repo.get_incident(session, tenant_id=tenant_a, incident_id=incident_b.id) is None
        with pytest.raises(repo.TenantScopeError):
            repo.require_incident(session, tenant_id=tenant_a, incident_id=incident_b.id)

        assert [item.id for item in repo.list_incidents(session, tenant_id=tenant_a)] == [
            incident_a.id
        ]
        assert [item.id for item in repo.list_incidents(session, tenant_id=tenant_b)] == [
            incident_b.id
        ]


def test_status_update_cannot_cross_tenants(db: Engine) -> None:
    with db.begin() as connection:
        tenant_a, _ = _tenant_and_site(connection)
        tenant_b, _ = _tenant_and_site(connection)

    with Session(db) as session:
        incident_b = repo.create_incident(
            session, tenant_id=tenant_b, fingerprint="fp-b", severity="error"
        )
        session.commit()

        with pytest.raises(repo.TenantScopeError):
            repo.update_incident_status(
                session,
                tenant_id=tenant_a,
                incident_id=incident_b.id,
                to_status="TRIAGING",
                actor="operator@example",
            )
        session.rollback()

        unchanged = repo.require_incident(session, tenant_id=tenant_b, incident_id=incident_b.id)
        assert unchanged.status == "NEW"
        assert session.scalar(select(func.count()).select_from(IncidentStateHistory)) == 0


def test_status_update_appends_history_and_manages_resolved_at(db: Engine) -> None:
    with db.begin() as connection:
        tenant_id, _ = _tenant_and_site(connection)

    with Session(db) as session:
        incident = repo.create_incident(
            session, tenant_id=tenant_id, fingerprint="fp", severity="warning"
        )
        session.commit()

        repo.update_incident_status(
            session,
            tenant_id=tenant_id,
            incident_id=incident.id,
            to_status="RESOLVED",
            actor="operator@example",
            reason="load back to baseline",
        )
        session.commit()
        history = session.scalars(
            select(IncidentStateHistory).where(IncidentStateHistory.incident_id == incident.id)
        ).all()
        assert [(row.from_status, row.to_status, row.actor) for row in history] == [
            ("NEW", "RESOLVED", "operator@example")
        ]
        assert incident.resolved_at is not None

        repo.update_incident_status(
            session,
            tenant_id=tenant_id,
            incident_id=incident.id,
            to_status="INVESTIGATING",
            actor="operator@example",
        )
        assert incident.resolved_at is None


def test_link_rejects_a_site_from_another_tenant(db: Engine) -> None:
    with db.begin() as connection:
        tenant_a, _ = _tenant_and_site(connection)
        _, site_b = _tenant_and_site(connection)

    with Session(db) as session:
        incident_a = repo.create_incident(
            session, tenant_id=tenant_a, fingerprint="fp-a", severity="warning"
        )
        session.commit()

        with pytest.raises(repo.TenantScopeError, match="site"):
            repo.link_incident(
                session,
                tenant_id=tenant_a,
                incident_id=incident_a.id,
                site_id=site_b,
                local_incident_id="local-1",
                version=1,
            )


def test_links_are_idempotent_and_versions_never_go_backwards(db: Engine) -> None:
    with db.begin() as connection:
        tenant_id, site_id = _tenant_and_site(connection)

    with Session(db) as session:
        incident = repo.create_incident(
            session, tenant_id=tenant_id, fingerprint="fp", severity="warning"
        )
        session.commit()

        first = repo.link_incident(
            session,
            tenant_id=tenant_id,
            incident_id=incident.id,
            site_id=site_id,
            local_incident_id="local-1",
            version=1,
        )
        replay = repo.link_incident(
            session,
            tenant_id=tenant_id,
            incident_id=incident.id,
            site_id=site_id,
            local_incident_id="local-1",
            version=1,
        )
        newer = repo.link_incident(
            session,
            tenant_id=tenant_id,
            incident_id=incident.id,
            site_id=site_id,
            local_incident_id="local-1",
            version=3,
        )
        stale = repo.link_incident(
            session,
            tenant_id=tenant_id,
            incident_id=incident.id,
            site_id=site_id,
            local_incident_id="local-1",
            version=2,
        )
        session.commit()

        keys = {
            (link.incident_id, link.site_id, link.local_incident_id)
            for link in (first, replay, newer, stale)
        }
        assert len(keys) == 1
        assert stale.last_version == 3
        assert session.scalar(select(func.count()).select_from(IncidentLink)) == 1


def test_audit_event_is_written_with_the_tenant(db: Engine) -> None:
    with db.begin() as connection:
        tenant_id, _ = _tenant_and_site(connection)

    with Session(db) as session:
        incident = repo.create_incident(
            session, tenant_id=tenant_id, fingerprint="fp", severity="warning"
        )
        audit = repo.record_audit_event(
            session,
            tenant_id=tenant_id,
            actor="operator@example",
            action="incident.approve",
            subject=str(incident.id),
            details={"decision": "approve"},
        )
        session.commit()

        stored = session.scalars(select(AuditEvent).where(AuditEvent.id == audit.id)).one()
        assert stored.tenant_id == tenant_id
        assert stored.details == {"decision": "approve"}


def test_events_are_scoped_and_ordered(db: Engine) -> None:
    with db.begin() as connection:
        tenant_a, site_a = _tenant_and_site(connection)
        tenant_b, site_b = _tenant_and_site(connection)

    now = datetime.now(UTC)
    with Session(db) as session:
        for index in range(3):
            repo.create_event(
                session,
                tenant_id=tenant_a,
                site_id=site_a,
                event_id=f"evt-a-{index}",
                event_type="com.aiops.alert.firing.v1",
                entity_ref={"kind": "node", "id": "n1"},
                severity="warning",
                occurred_at=now - timedelta(minutes=index),
            )
        repo.create_event(
            session,
            tenant_id=tenant_b,
            site_id=site_b,
            event_id="evt-b-0",
            event_type="com.aiops.alert.firing.v1",
            entity_ref={"kind": "node", "id": "n2"},
            severity="error",
            occurred_at=now,
        )
        session.commit()

        events = repo.list_events(session, tenant_id=tenant_a)
        assert [event.event_id for event in events] == ["evt-a-0", "evt-a-1", "evt-a-2"]
        assert repo.list_events(session, tenant_id=tenant_b)[0].event_id == "evt-b-0"
        assert repo.list_events(session, tenant_id=tenant_a, site_id=site_b) == []
        assert session.scalar(select(func.count()).select_from(Incident)) == 0
