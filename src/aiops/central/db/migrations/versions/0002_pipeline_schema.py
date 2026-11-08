"""pipeline schema: events, incidents, links, state history, audit

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08

Hand-written for the same reason as 0001: the schema is the contract and the
constraint names must match ``aiops.central.db.models`` exactly. Column
definitions mirror SPEC section 10 and the unique keys in SPEC section 1.

No table is dropped or narrowed, so this revision is expand-only and safe to
apply to a database that already serves traffic.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEVERITIES = ("info", "warning", "error", "critical")
INCIDENT_STATUSES = (
    "NEW",
    "TRIAGING",
    "INVESTIGATING",
    "AWAITING_APPROVAL",
    "REMEDIATING",
    "VERIFYING",
    "RESOLVED",
    "ESCALATED",
    "FALSE_POSITIVE",
    "FAILED",
)

_severity_list = ", ".join(f"'{value}'" for value in SEVERITIES)
_status_list = ", ".join(f"'{value}'" for value in INCIDENT_STATUSES)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _id_column() -> sa.Column:
    return sa.Column(
        "id",
        _uuid(),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _tenant_column() -> sa.Column:
    return sa.Column("tenant_id", _uuid(), nullable=False)


def _now_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "events",
        _id_column(),
        _tenant_column(),
        sa.Column("site_id", _uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=120), nullable=False),
        sa.Column("entity_ref", postgresql.JSONB(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        _now_column("received_at"),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
            name="fk_events_site_id_sites",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("site_id", "event_id", name="uq_events_site_id_event_id"),
        sa.CheckConstraint(f"severity IN ({_severity_list})", name="severity_allowed"),
    )
    op.create_index("ix_events_tenant_id_occurred_at", "events", ["tenant_id", "occurred_at"])
    op.create_index("ix_events_site_id_occurred_at", "events", ["site_id", "occurred_at"])

    op.create_table(
        "incidents",
        _id_column(),
        _tenant_column(),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'NEW'"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("fingerprint", sa.String(length=300), nullable=False),
        _now_column("opened_at"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _now_column("created_at"),
        _now_column("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_incidents"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_incidents_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"status IN ({_status_list})", name="status_allowed"),
        sa.CheckConstraint(f"severity IN ({_severity_list})", name="severity_allowed"),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at",
            name="resolved_after_opened",
        ),
    )
    op.create_index("ix_incidents_tenant_id_opened_at", "incidents", ["tenant_id", "opened_at"])

    op.create_table(
        "incident_links",
        sa.Column("incident_id", _uuid(), nullable=False),
        sa.Column("site_id", _uuid(), nullable=False),
        sa.Column("local_incident_id", sa.String(length=200), nullable=False),
        sa.Column(
            "last_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        _now_column("updated_at"),
        sa.PrimaryKeyConstraint(
            "incident_id",
            "site_id",
            "local_incident_id",
            name="pk_incident_links",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_incident_links_incident_id_incidents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
            name="fk_incident_links_site_id_sites",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "site_id",
            "local_incident_id",
            name="uq_incident_links_site_id_local_incident_id",
        ),
        sa.CheckConstraint("last_version >= 1", name="version_positive"),
    )

    op.create_table(
        "incident_state_history",
        _id_column(),
        sa.Column("incident_id", _uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        _now_column("at"),
        sa.PrimaryKeyConstraint("id", name="pk_incident_state_history"),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name="fk_incident_state_history_incident_id_incidents",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"to_status IN ({_status_list})", name="to_status_allowed"),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_status_list})",
            name="from_status_allowed",
        ),
    )
    op.create_index(
        "ix_incident_state_history_incident_id_at",
        "incident_state_history",
        ["incident_id", "at"],
    )

    op.create_table(
        "audit_events",
        _id_column(),
        _tenant_column(),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=True),
        _now_column("at"),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_audit_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_audit_events_tenant_id_at", "audit_events", ["tenant_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_tenant_id_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(
        "ix_incident_state_history_incident_id_at",
        table_name="incident_state_history",
    )
    op.drop_table("incident_state_history")
    op.drop_table("incident_links")
    op.drop_index("ix_incidents_tenant_id_opened_at", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_events_site_id_occurred_at", table_name="events")
    op.drop_index("ix_events_tenant_id_occurred_at", table_name="events")
    op.drop_table("events")
