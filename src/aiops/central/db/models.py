"""Central table models.

S1-A2 added ``tenants``, ``sites`` and ``users``; S2-A1 adds the pipeline
tables (``events``, ``incidents``, ``incident_links``,
``incident_state_history``, ``audit_events``).

Every tenant-owned table carries a non-null ``tenant_id`` foreign key. The
application derives the tenant from the authenticated identity; this column is
what enforces that a query cannot silently cross tenants.

Enumerations are CHECK constraints rather than PostgreSQL ENUM types: adding a
value to a native enum needs its own migration and cannot run inside some
transaction patterns, which fights the expand-and-contract rule.

``events.payload``, ``events.entity_ref`` and ``audit_events.details`` are
JSONB. Their shape is validated at ingestion against
``contracts/schemas/*.json``; the database only guarantees that the column is
an object, not that every key is correct.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, get_args

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from aiops.central.db.base import Base
from aiops.contracts.events import Severity
from aiops.contracts.incidents import IncidentStatus

SITE_STATUSES: tuple[str, ...] = ("CONNECTED", "DEGRADED", "OFFLINE", "UNKNOWN")
USER_ROLES: tuple[str, ...] = ("operator", "approver", "viewer")
SEVERITIES: tuple[str, ...] = get_args(Severity)
INCIDENT_STATUSES: tuple[str, ...] = get_args(IncidentStatus)


def _quoted(values: tuple[str, ...]) -> str:
    """Render values for a CHECK constraint, deterministically."""
    return ", ".join(f"'{value}'" for value in values)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_sites_tenant_name"),
        CheckConstraint(
            "status IN ('CONNECTED', 'DEGRADED', 'OFFLINE', 'UNKNOWN')",
            name="status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'UNKNOWN'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are stored lowercase by the application before insert/update.
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        CheckConstraint(
            "role IN ('operator', 'approver', 'viewer')",
            name="role_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Event(Base):
    """One observation forwarded by a site; duplicates are expected.

    ``event_id`` is generated at the site, not here. The unique key
    ``(site_id, event_id)`` is what makes a replayed batch harmless.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("site_id", "event_id", name="uq_events_site_id_event_id"),
        CheckConstraint(f"severity IN ({_quoted(SEVERITIES)})", name="severity_allowed"),
        Index("ix_events_tenant_id_occurred_at", "tenant_id", "occurred_at"),
        Index("ix_events_site_id_occurred_at", "site_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column("type", String(120), nullable=False)
    entity_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class Incident(Base):
    """The central incident, correlated from one or more site-local incidents."""

    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(f"status IN ({_quoted(INCIDENT_STATUSES)})", name="status_allowed"),
        CheckConstraint(f"severity IN ({_quoted(SEVERITIES)})", name="severity_allowed"),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at",
            name="resolved_after_opened",
        ),
        Index("ix_incidents_tenant_id_opened_at", "tenant_id", "opened_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'NEW'"))
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(300), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IncidentLink(Base):
    """Maps a site-local incident to the central incident, with its version.

    ``(site_id, local_incident_id)`` is unique: a site-local incident belongs to
    exactly one central incident, so a replayed version can be acknowledged
    instead of creating a duplicate.
    """

    __tablename__ = "incident_links"
    __table_args__ = (
        UniqueConstraint(
            "site_id",
            "local_incident_id",
            name="uq_incident_links_site_id_local_incident_id",
        ),
        CheckConstraint("last_version >= 1", name="version_positive"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    local_incident_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    last_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IncidentStateHistory(Base):
    """Append-only transition log. One row per accepted state change.

    ``from_status`` is null for the row that creates the incident. The table has
    no update path in the application; a database-level append-only trigger is
    deferred to the audit hardening task (see ``db/README.md``).
    """

    __tablename__ = "incident_state_history"
    __table_args__ = (
        CheckConstraint(f"to_status IN ({_quoted(INCIDENT_STATUSES)})", name="to_status_allowed"),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_quoted(INCIDENT_STATUSES)})",
            name="from_status_allowed",
        ),
        Index("ix_incident_state_history_incident_id_at", "incident_id", "at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditEvent(Base):
    """Append-only record of sensitive actions (login, approval, policy edit)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_tenant_id_at", "tenant_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
