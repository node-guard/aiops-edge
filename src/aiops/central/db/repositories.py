"""Tenant-aware data access for the central control plane (S2-A2).

Every public function takes ``tenant_id`` as a required keyword argument. The
tenant is derived from the authenticated identity by the API/edge layer; it is
never read from a request body. Keeping it required (no default, no ``None``)
means a caller cannot "forget" the filter and silently query across tenants.

Queries against tenant-owned tables go through :func:`tenant_select`, which
always adds the ``tenant_id`` predicate. Tables without their own ``tenant_id``
(``incident_links``, ``incident_state_history``) are only reachable after the
parent incident has been loaded *with* the tenant filter, or after the referenced
site has been checked against the same tenant.

Session handling (commit/rollback) belongs to the caller; functions flush so the
new row is visible inside the caller's transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from aiops.central.db.base import Base
from aiops.central.db.models import (
    INCIDENT_STATUSES,
    SEVERITIES,
    AuditEvent,
    Event,
    Incident,
    IncidentLink,
    IncidentStateHistory,
    Site,
)
from aiops.common.time import utcnow

INCIDENT_OPEN_STATUSES: tuple[str, ...] = tuple(
    status for status in INCIDENT_STATUSES if status not in {"RESOLVED", "FALSE_POSITIVE"}
)


class TenantScopeError(LookupError):
    """A row does not exist in the caller's tenant (or does not exist at all).

    The same error covers both cases on purpose: the caller must not learn
    whether an id exists in another tenant.
    """


def tenant_select[Model: Base](model: type[Model], *, tenant_id: uuid.UUID) -> Select[tuple[Model]]:
    """Start a query that is already scoped to one tenant.

    This is the only place a raw ``select()`` on a tenant-owned table is built.
    """
    column = getattr(model, "tenant_id")  # noqa: B009 - generic tenant column
    return select(model).where(column == tenant_id)


def _require_tenant_id(tenant_id: uuid.UUID | None) -> uuid.UUID:
    if tenant_id is None:
        raise ValueError("tenant_id is required")
    return tenant_id


def create_event(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    event_id: str,
    event_type: str,
    entity_ref: dict[str, Any],
    severity: str,
    occurred_at: datetime,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Insert one event; a duplicate ``(site_id, event_id)`` is the caller's to handle."""
    _require_tenant_id(tenant_id)
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity {severity!r}")
    event = Event(
        tenant_id=tenant_id,
        site_id=site_id,
        event_id=event_id,
        event_type=event_type,
        entity_ref=entity_ref,
        severity=severity,
        occurred_at=occurred_at,
        payload={} if payload is None else payload,
    )
    session.add(event)
    session.flush()
    return event


def list_events(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[Event]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    statement = (
        tenant_select(Event, tenant_id=tenant_id).order_by(Event.occurred_at.desc()).limit(limit)
    )
    if site_id is not None:
        statement = statement.where(Event.site_id == site_id)
    return list(session.scalars(statement))


def create_incident(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    fingerprint: str,
    severity: str,
    status: str = "NEW",
    opened_at: datetime | None = None,
) -> Incident:
    _require_tenant_id(tenant_id)
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity {severity!r}")
    if status not in INCIDENT_STATUSES:
        raise ValueError(f"unknown incident status {status!r}")
    incident = Incident(
        tenant_id=tenant_id,
        fingerprint=fingerprint,
        severity=severity,
        status=status,
        opened_at=utcnow() if opened_at is None else opened_at,
    )
    session.add(incident)
    session.flush()
    return incident


def get_incident(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    incident_id: uuid.UUID,
    for_update: bool = False,
) -> Incident | None:
    statement = tenant_select(Incident, tenant_id=tenant_id).where(Incident.id == incident_id)
    if for_update:
        statement = statement.with_for_update()
    return session.scalars(statement).one_or_none()


def require_incident(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    incident_id: uuid.UUID,
    for_update: bool = False,
) -> Incident:
    incident = get_incident(
        session, tenant_id=tenant_id, incident_id=incident_id, for_update=for_update
    )
    if incident is None:
        raise TenantScopeError(f"incident {incident_id} is not visible in this tenant")
    return incident


def list_incidents(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    status: str | None = None,
    open_only: bool = False,
    limit: int = 50,
) -> list[Incident]:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if status is not None and status not in INCIDENT_STATUSES:
        raise ValueError(f"unknown incident status {status!r}")
    statement = (
        tenant_select(Incident, tenant_id=tenant_id)
        .order_by(Incident.opened_at.desc())
        .limit(limit)
    )
    if status is not None:
        statement = statement.where(Incident.status == status)
    if open_only:
        statement = statement.where(Incident.status.in_(INCIDENT_OPEN_STATUSES))
    return list(session.scalars(statement))


def update_incident_status(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    incident_id: uuid.UUID,
    to_status: str,
    actor: str,
    reason: str | None = None,
) -> Incident:
    """Change status and append the transition in the same transaction."""
    if to_status not in INCIDENT_STATUSES:
        raise ValueError(f"unknown incident status {to_status!r}")
    if not actor:
        raise ValueError("actor is required")

    incident = require_incident(
        session, tenant_id=tenant_id, incident_id=incident_id, for_update=True
    )
    from_status = incident.status
    if from_status == to_status:
        return incident

    session.add(
        IncidentStateHistory(
            incident_id=incident.id,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            reason=reason,
        )
    )
    incident.status = to_status
    if to_status == "RESOLVED":
        incident.resolved_at = utcnow()
    elif to_status in INCIDENT_OPEN_STATUSES:
        incident.resolved_at = None
    session.flush()
    return incident


def link_incident(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    incident_id: uuid.UUID,
    site_id: uuid.UUID,
    local_incident_id: str,
    version: int,
) -> IncidentLink:
    """Map a site-local incident version onto a central incident.

    Both the incident and the site are checked against ``tenant_id`` first;
    ``incident_links`` has no tenant column of its own.
    """
    if version < 1:
        raise ValueError("version must be >= 1")
    incident = require_incident(session, tenant_id=tenant_id, incident_id=incident_id)
    site = session.scalars(
        tenant_select(Site, tenant_id=tenant_id).where(Site.id == site_id)
    ).one_or_none()
    if site is None:
        raise TenantScopeError(f"site {site_id} is not visible in this tenant")

    link = session.scalars(
        select(IncidentLink).where(
            IncidentLink.site_id == site_id,
            IncidentLink.local_incident_id == local_incident_id,
        )
    ).one_or_none()
    if link is None:
        link = IncidentLink(
            incident_id=incident.id,
            site_id=site_id,
            local_incident_id=local_incident_id,
            last_version=version,
        )
        session.add(link)
    elif version > link.last_version:
        link.last_version = version
    session.flush()
    return link


def record_audit_event(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor: str,
    action: str,
    subject: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    if not actor or not action:
        raise ValueError("actor and action are required")
    audit = AuditEvent(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        subject=subject,
        details={} if details is None else details,
    )
    session.add(audit)
    session.flush()
    return audit
