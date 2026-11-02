"""Central configuration read from the environment.

Settings are validated once at startup so a misconfigured deployment fails fast
instead of serving traffic with a broken database. Values are never logged: the
database URL contains the PostgreSQL password.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_WORKER_POLL_SECONDS = 30
MIN_WORKER_POLL_SECONDS = 5


class ConfigError(RuntimeError):
    """Raised when a required environment setting is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_env: str = "development"
    session_secret: str | None = None
    llm_provider: str = "cloud"
    llm_model: str | None = None
    worker_poll_seconds: int = DEFAULT_WORKER_POLL_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env

        database_url = source.get("DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigError("DATABASE_URL is required")
        if not database_url.startswith("postgresql"):
            raise ConfigError(
                "DATABASE_URL must be a PostgreSQL URL, e.g. postgresql+psycopg://..."
            )

        raw_poll = source.get("WORKER_POLL_SECONDS", "").strip()
        if raw_poll:
            try:
                poll_seconds = int(raw_poll)
            except ValueError as exc:
                raise ConfigError("WORKER_POLL_SECONDS must be an integer") from exc
        else:
            poll_seconds = DEFAULT_WORKER_POLL_SECONDS
        if poll_seconds < MIN_WORKER_POLL_SECONDS:
            raise ConfigError(f"WORKER_POLL_SECONDS must be >= {MIN_WORKER_POLL_SECONDS}")

        return cls(
            database_url=database_url,
            app_env=source.get("APP_ENV", "development").strip() or "development",
            session_secret=source.get("SESSION_SECRET") or None,
            llm_provider=source.get("LLM_PROVIDER", "cloud").strip() or "cloud",
            llm_model=source.get("LLM_MODEL") or None,
            worker_poll_seconds=poll_seconds,
        )
