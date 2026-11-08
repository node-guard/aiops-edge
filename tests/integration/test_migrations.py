"""Migration round-trip against a real PostgreSQL (S1-A2).

Skipped unless ``AIOPS_TEST_DATABASE_URL`` is set, so a normal ``make check``
never touches a database. The test drops every table it creates, so point it at
a throwaway database only.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
EXPECTED_TABLES = {
    "tenants",
    "sites",
    "users",
    "events",
    "incidents",
    "incident_links",
    "incident_state_history",
    "audit_events",
}


def _database_url() -> str:
    url = os.environ.get("AIOPS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AIOPS_TEST_DATABASE_URL is not set")
    return url


@pytest.fixture()
def alembic_config() -> Iterator[Config]:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", _database_url())
    yield config


def _tables() -> set[str]:
    engine = create_engine(_database_url())
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_base_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    assert EXPECTED_TABLES <= _tables()


def test_downgrade_removes_base_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    assert not (EXPECTED_TABLES & _tables())


@pytest.fixture()
def db(alembic_config: Config) -> Iterator[Engine]:
    """A migrated database, emptied afterwards so tests do not interfere."""
    command.upgrade(alembic_config, "head")
    engine = create_engine(_database_url())
    yield engine
    with engine.begin() as connection:
        for table in (
            "audit_events",
            "incident_state_history",
            "incident_links",
            "events",
            "incidents",
            "sites",
            "users",
            "tenants",
        ):
            connection.execute(text(f"DELETE FROM {table}"))
    engine.dispose()


def _seed(connection: Connection) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id, site_id, incident_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    connection.execute(
        text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
        {"id": tenant_id, "name": f"tenant-{tenant_id}"},
    )
    connection.execute(
        text("INSERT INTO sites (id, tenant_id, name) VALUES (:id, :tenant, :name)"),
        {"id": site_id, "tenant": tenant_id, "name": f"site-{site_id}"},
    )
    connection.execute(
        text(
            "INSERT INTO incidents (id, tenant_id, severity, fingerprint) "
            "VALUES (:id, :tenant, 'warning', :fingerprint)"
        ),
        {"id": incident_id, "tenant": tenant_id, "fingerprint": str(incident_id)},
    )
    return tenant_id, site_id, incident_id


def test_replayed_event_is_rejected_by_the_unique_key(db: Engine) -> None:
    with db.begin() as connection:
        tenant_id, site_id, _ = _seed(connection)
        insert = text(
            "INSERT INTO events (tenant_id, site_id, event_id, type, entity_ref, "
            "severity, occurred_at) VALUES (:tenant, :site, :event, 't', '{}', "
            "'warning', now())"
        )
        values = {"tenant": tenant_id, "site": site_id, "event": "evt-1"}
        connection.execute(insert, values)
        with pytest.raises(IntegrityError, match="uq_events_site_id_event_id"):
            connection.execute(insert, values)


def test_deleting_an_incident_cascades_links_and_history(db: Engine) -> None:
    with db.begin() as connection:
        _, site_id, incident_id = _seed(connection)
        connection.execute(
            text(
                "INSERT INTO incident_links (incident_id, site_id, local_incident_id) "
                "VALUES (:incident, :site, 'local-1')"
            ),
            {"incident": incident_id, "site": site_id},
        )
        connection.execute(
            text(
                "INSERT INTO incident_state_history (incident_id, to_status, actor) "
                "VALUES (:incident, 'NEW', 'edge')"
            ),
            {"incident": incident_id},
        )
        connection.execute(text("DELETE FROM incidents WHERE id = :id"), {"id": incident_id})
        assert connection.scalar(text("SELECT count(*) FROM incident_links")) == 0
        assert connection.scalar(text("SELECT count(*) FROM incident_state_history")) == 0


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("severity", "fatal", "ck_incidents_severity_allowed"),
        ("status", "OPEN", "ck_incidents_status_allowed"),
    ],
)
def test_invalid_enum_values_are_rejected(
    db: Engine, column: str, value: str, constraint: str
) -> None:
    with db.begin() as connection:
        tenant_id = uuid.uuid4()
        connection.execute(
            text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
            {"id": tenant_id, "name": f"tenant-{tenant_id}"},
        )
        with pytest.raises(IntegrityError, match=constraint):
            connection.execute(
                text(
                    "INSERT INTO incidents (tenant_id, severity, fingerprint, status) "
                    "VALUES (:tenant, :severity, 'fp', :status)"
                ),
                {
                    "tenant": tenant_id,
                    "severity": value if column == "severity" else "warning",
                    "status": value if column == "status" else "NEW",
                },
            )
