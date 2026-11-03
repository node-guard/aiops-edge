"""Migration round-trip against a real PostgreSQL (S1-A2).

Skipped unless ``AIOPS_TEST_DATABASE_URL`` is set, so a normal ``make check``
never touches a database. The test drops every table it creates, so point it at
a throwaway database only.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
EXPECTED_TABLES = {"tenants", "sites", "users"}


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
