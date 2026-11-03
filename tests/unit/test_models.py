"""Schema invariants for the base models (S1-A2).

These run without a database: they assert the metadata that the baseline
migration must mirror.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint

from aiops.central.db import models  # noqa: F401  (registers tables on Base.metadata)
from aiops.central.db.base import Base
from aiops.central.db.models import SITE_STATUSES, USER_ROLES


def _check_sql(table_name: str, constraint_name: str) -> str:
    table = Base.metadata.tables[table_name]
    for constraint in table.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == constraint_name:
            return str(constraint.sqltext)
    raise AssertionError(f"{constraint_name} not found on {table_name}")


def test_every_tenant_owned_table_carries_a_tenant_fk() -> None:
    owned = [table for name, table in Base.metadata.tables.items() if name != "tenants"]

    assert {table.name for table in owned} == {"sites", "users"}
    for table in owned:
        column = table.c["tenant_id"]
        assert column.nullable is False
        (foreign_key,) = column.foreign_keys
        assert foreign_key.column.table.name == "tenants"
        assert foreign_key.ondelete == "RESTRICT"


def test_primary_keys_follow_the_naming_convention() -> None:
    assert Base.metadata.tables["tenants"].primary_key.name == "pk_tenants"
    assert Base.metadata.tables["sites"].primary_key.name == "pk_sites"
    assert Base.metadata.tables["users"].primary_key.name == "pk_users"


def test_ids_and_timestamps_have_server_defaults() -> None:
    for table in Base.metadata.tables.values():
        assert table.c["id"].server_default is not None, table.name
        assert table.c["created_at"].server_default is not None, table.name


def test_site_status_values_are_constrained() -> None:
    sql = _check_sql("sites", "ck_sites_status_allowed")

    for value in SITE_STATUSES:
        assert f"'{value}'" in sql


def test_user_role_values_are_constrained() -> None:
    sql = _check_sql("users", "ck_users_role_allowed")

    for value in USER_ROLES:
        assert f"'{value}'" in sql


def test_email_is_unique_per_tenant() -> None:
    users = Base.metadata.tables["users"]
    unique_column_sets = {
        tuple(sorted(column.name for column in constraint.columns))
        for constraint in users.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("email", "tenant_id") in unique_column_sets


def test_tenant_id_is_indexed() -> None:
    for table_name in ("sites", "users"):
        table = Base.metadata.tables[table_name]
        indexed = {column.name for index in table.indexes for column in index.columns}
        assert "tenant_id" in indexed, table_name
