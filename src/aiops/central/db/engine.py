"""Database engine and dependency probes for the central control plane."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from aiops.common.redact import redact

_MAX_DETAIL_CHARS = 300


def create_db_engine(database_url: str) -> Engine:
    """Build the sync engine shared by the API and the worker.

    ``pool_pre_ping`` avoids handing out connections that PostgreSQL closed on
    restart or on a compose recreate, the usual failure mode in the lab.
    """
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    ok: bool
    latency_ms: float
    detail: str | None = None


def check_database(engine: Engine) -> DependencyCheck:
    """Run a minimal query and report latency.

    The error detail is redacted and truncated: driver messages can echo the
    connection string, and health output may end up in logs or a dashboard.
    """
    started = perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        return DependencyCheck(
            name="postgres",
            ok=False,
            latency_ms=_elapsed_ms(started),
            detail=redact(str(exc))[:_MAX_DETAIL_CHARS],
        )
    return DependencyCheck(name="postgres", ok=True, latency_ms=_elapsed_ms(started))


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)
