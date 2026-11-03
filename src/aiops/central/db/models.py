"""Base models for S1-A2: tenants, sites and users.

Every tenant-owned table carries a non-null ``tenant_id`` foreign key. The
application derives the tenant from the authenticated identity; this column is
what enforces that a query cannot silently cross tenants.

Enumerations are CHECK constraints rather than PostgreSQL ENUM types: adding a
value to a native enum needs its own migration and cannot run inside some
transaction patterns, which fights the expand-and-contract rule.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from aiops.central.db.base import Base

SITE_STATUSES: tuple[str, ...] = ("CONNECTED", "DEGRADED", "OFFLINE", "UNKNOWN")
USER_ROLES: tuple[str, ...] = ("operator", "approver", "viewer")


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
