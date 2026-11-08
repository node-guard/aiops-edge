"""Schema invariants for the central models.

These run without a database: they assert the metadata that the migrations must
mirror. Behavioural tests (unique violations, cascades, CHECK failures) need a
live PostgreSQL and live with the repositories in S2-A2.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint

from aiops.central.db import models  # noqa: F401  (registers tables on Base.metadata)
from aiops.central.db.base import Base
from aiops.central.db.models import (
    INCIDENT_STATUSES,
    SEVERITIES,
    SITE_STATUSES,
    USER_ROLES,
)

TENANT_OWNED = {"sites", "users", "events", "incidents", "audit_events"}

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


def _check_sql(table_name: str, constraint_name: str) -> str:
    table = Base.metadata.tables[table_name]
    for constraint in table.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == constraint_name:
            return str(constraint.sqltext)
    raise AssertionError(f"{constraint_name} not found on {table_name}")


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        tuple(sorted(column.name for column in constraint.columns))
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _indexed_columns(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {column.name for index in table.indexes for column in index.columns}


def test_table_inventory_is_exactly_sprint_two() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_tenant_owned_table_carries_a_tenant_fk() -> None:
    for table_name in TENANT_OWNED:
        column = Base.metadata.tables[table_name].c["tenant_id"]
        assert column.nullable is False, table_name
        (foreign_key,) = column.foreign_keys
        assert foreign_key.column.table.name == "tenants", table_name
        assert foreign_key.ondelete == "RESTRICT", table_name


def test_primary_keys_follow_the_naming_convention() -> None:
    for table_name in EXPECTED_TABLES:
        assert Base.metadata.tables[table_name].primary_key.name == f"pk_{table_name}"


def test_ids_and_timestamps_have_server_defaults() -> None:
    for table_name in EXPECTED_TABLES:
        table = Base.metadata.tables[table_name]
        if "id" in table.c:
            assert table.c["id"].server_default is not None, table_name

    for table_name, column in (
        ("tenants", "created_at"),
        ("sites", "created_at"),
        ("users", "created_at"),
        ("incidents", "created_at"),
        ("events", "received_at"),
        ("incident_state_history", "at"),
        ("audit_events", "at"),
        ("incident_links", "updated_at"),
    ):
        table = Base.metadata.tables[table_name]
        assert table.c[column].server_default is not None, (table_name, column)


def test_site_status_values_are_constrained() -> None:
    sql = _check_sql("sites", "ck_sites_status_allowed")

    for value in SITE_STATUSES:
        assert f"'{value}'" in sql


def test_user_role_values_are_constrained() -> None:
    sql = _check_sql("users", "ck_users_role_allowed")

    for value in USER_ROLES:
        assert f"'{value}'" in sql


def test_severity_values_are_constrained() -> None:
    for table_name in ("events", "incidents"):
        sql = _check_sql(table_name, f"ck_{table_name}_severity_allowed")
        for value in SEVERITIES:
            assert f"'{value}'" in sql, (table_name, value)


def test_incident_status_values_are_constrained() -> None:
    sql = _check_sql("incidents", "ck_incidents_status_allowed")
    assert len(INCIDENT_STATUSES) == 10
    for value in INCIDENT_STATUSES:
        assert f"'{value}'" in sql

    history = Base.metadata.tables["incident_state_history"]
    assert _check_sql("incident_state_history", "ck_incident_state_history_to_status_allowed")
    assert _check_sql("incident_state_history", "ck_incident_state_history_from_status_allowed")
    assert history.c["from_status"].nullable is True
    assert history.c["to_status"].nullable is False


def test_email_is_unique_per_tenant() -> None:
    assert ("email", "tenant_id") in _unique_column_sets("users")


def test_events_are_idempotent_per_site() -> None:
    assert ("event_id", "site_id") in _unique_column_sets("events")


def test_a_local_incident_maps_to_one_central_incident() -> None:
    assert ("local_incident_id", "site_id") in _unique_column_sets("incident_links")


def test_incident_links_use_a_composite_key_and_cascade_from_the_incident() -> None:
    table = Base.metadata.tables["incident_links"]
    assert [column.name for column in table.primary_key.columns] == [
        "incident_id",
        "site_id",
        "local_incident_id",
    ]

    cascades = {foreign_key.parent.name: foreign_key.ondelete for foreign_key in table.foreign_keys}
    assert cascades == {"incident_id": "CASCADE", "site_id": "RESTRICT"}

    version_check = _check_sql("incident_links", "ck_incident_links_version_positive")
    assert version_check == "last_version >= 1"


def test_state_history_cascades_with_its_incident() -> None:
    table = Base.metadata.tables["incident_state_history"]
    (foreign_key,) = table.c["incident_id"].foreign_keys
    assert foreign_key.column.table.name == "incidents"
    assert foreign_key.ondelete == "CASCADE"


def test_resolved_incident_cannot_precede_its_open_time() -> None:
    sql = _check_sql("incidents", "ck_incidents_resolved_after_opened")
    assert "resolved_at" in sql and "opened_at" in sql


def test_jsonb_columns_default_to_an_empty_object() -> None:
    for table_name, column_name in (
        ("events", "payload"),
        ("audit_events", "details"),
    ):
        column = Base.metadata.tables[table_name].c[column_name]
        assert column.nullable is False
        assert "'{}'::jsonb" in str(column.server_default.arg)

    assert Base.metadata.tables["events"].c["entity_ref"].nullable is False


def test_tenant_queries_are_indexed() -> None:
    for table_name in TENANT_OWNED:
        assert "tenant_id" in _indexed_columns(table_name), table_name

    incidents = {index.name for index in Base.metadata.tables["incidents"].indexes}
    assert "ix_incidents_tenant_id_opened_at" in incidents
