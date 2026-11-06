"""Unit tests for the shop-demo application (S1-B2)."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "deploy" / "shop-demo" / "app" / "shop_demo.py"


def load_app() -> ModuleType:
    spec = importlib.util.spec_from_file_location("shop_demo_app", APP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["shop_demo_app"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def shop_demo() -> ModuleType:
    return load_app()


@pytest.fixture()
def client(shop_demo: ModuleType):
    with TestClient(shop_demo.app) as test_client:
        yield test_client


def test_index_returns_service_metadata(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "shop-demo"
    assert "/health/ready" in body["endpoints"]


def test_liveness_stays_up_when_database_is_down(
    client: TestClient, shop_demo: ModuleType, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(shop_demo, "check_database", lambda: (False, "OperationalError"))
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_ok_when_database_is_up(
    client: TestClient, shop_demo: ModuleType, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(shop_demo, "check_database", lambda: (True, "up"))
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "up"}


def test_readiness_is_503_when_database_is_down(
    client: TestClient, shop_demo: ModuleType, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(shop_demo, "check_database", lambda: (False, "OperationalError"))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "OperationalError"}


def test_cpu_workload_is_bounded(client: TestClient):
    response = client.get("/work/cpu", params={"seconds": 0.2, "workers": 1})
    assert response.status_code == 200
    assert response.json() == {"workload": "cpu", "seconds": 0.2, "workers": 1}


def test_memory_workload_is_bounded(client: TestClient):
    response = client.get("/work/memory", params={"mb": 1, "seconds": 0.2})
    assert response.status_code == 200
    assert response.json() == {"workload": "memory", "mb": 1, "seconds": 0.2}


def test_workload_parameters_are_validated(client: TestClient):
    assert client.get("/work/cpu", params={"seconds": 0}).status_code == 422
    assert client.get("/work/cpu", params={"workers": 99}).status_code == 422
    assert client.get("/work/memory", params={"mb": 0}).status_code == 422


def test_injected_error_returns_500(client: TestClient):
    response = client.get("/work/fail", params={"mode": "error"})
    assert response.status_code == 500
    assert response.json()["detail"] == "injected application error"


def test_json_logs_redact_credentials(shop_demo: ModuleType):
    record = logging.LogRecord("shop-demo", logging.INFO, __file__, 1, "ready", None, None)
    record.fields = {"password": "hunter2", "token": "abc", "db_host": "shop-demo-db"}  # type: ignore[attr-defined]
    payload = json.loads(shop_demo.JsonFormatter().format(record))
    assert payload["password"] == "[REDACTED]"
    assert payload["token"] == "[REDACTED]"
    assert payload["db_host"] == "shop-demo-db"
    assert "hunter2" not in json.dumps(payload)
