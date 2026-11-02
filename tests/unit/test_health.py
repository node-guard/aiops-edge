"""Health endpoint behaviour for the central API skeleton (S1-A1)."""

from __future__ import annotations

from collections.abc import Iterator
from types import TracebackType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from aiops.central.api import main as api_main
from aiops.central.config import ConfigError, Settings


def _settings() -> Settings:
    return Settings(database_url="postgresql+psycopg://aiops:test@localhost:5432/aiops")


class _OkConnection:
    def __enter__(self) -> _OkConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    def execute(self, *_args: object, **_kwargs: object) -> None:
        return None


class _OkEngine:
    def connect(self) -> _OkConnection:
        return _OkConnection()

    def dispose(self) -> None:
        return None


class _BrokenEngine:
    def connect(self) -> None:
        raise SQLAlchemyError("connection refused (test)")

    def dispose(self) -> None:
        return None


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = api_main.create_app(_settings())
    app.dependency_overrides[api_main.get_engine] = lambda: _OkEngine()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_live_is_always_ok(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_reports_ok_when_postgres_answers(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"postgres": "ok"}
    assert body["checked_at"].endswith("+00:00")


def test_ready_returns_503_when_postgres_is_down() -> None:
    app = api_main.create_app(_settings())
    app.dependency_overrides[api_main.get_engine] = lambda: _BrokenEngine()
    with TestClient(app) as test_client:
        response = test_client.get("/health/ready")
    app.dependency_overrides.clear()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "connection refused" in body["checks"]["postgres"]


def test_dependencies_reports_latency(client: TestClient) -> None:
    response = client.get("/health/dependencies")

    assert response.status_code == 200
    postgres = response.json()["dependencies"]["postgres"]
    assert postgres["status"] == "ok"
    assert isinstance(postgres["latency_ms"], float)
    assert postgres["detail"] is None


def test_settings_reject_missing_database_url() -> None:
    with pytest.raises(ConfigError, match="DATABASE_URL is required"):
        Settings.from_env({})


def test_settings_reject_non_postgres_url() -> None:
    with pytest.raises(ConfigError, match="must be a PostgreSQL URL"):
        Settings.from_env({"DATABASE_URL": "sqlite:///local.db"})


def test_settings_defaults_are_applied() -> None:
    settings = Settings.from_env({"DATABASE_URL": "postgresql+psycopg://u:p@h:5432/db"})

    assert settings.app_env == "development"
    assert settings.llm_provider == "cloud"
    assert settings.worker_poll_seconds == 30
    assert settings.session_secret is None
