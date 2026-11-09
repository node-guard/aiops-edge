"""Shared PostgreSQL fixture for integration tests.

Skipped unless ``AIOPS_TEST_DATABASE_URL`` points at a throwaway database, so a
normal ``make check`` never touches a database. Point it only at a database you
can lose: the fixture deletes every row after each test.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

# Children before parents; tenants last (every tenant-owned table references it).
CLEANUP_ORDER = (
    "audit_events",
    "incident_state_history",
    "incident_links",
    "events",
    "incidents",
    "sites",
    "users",
    "tenants",
)


def database_url() -> str:
    url = os.environ.get("AIOPS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AIOPS_TEST_DATABASE_URL is not set")
    return url


@pytest.fixture()
def alembic_config() -> Iterator[Config]:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url())
    yield config


@pytest.fixture()
def db(alembic_config: Config) -> Iterator[Engine]:
    """A migrated database, emptied afterwards so tests do not interfere."""
    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url())
    yield engine
    with engine.begin() as connection:
        for table in CLEANUP_ORDER:
            connection.execute(text(f"DELETE FROM {table}"))
    engine.dispose()
