"""shop-demo: a disposable HTTP target for the lab fault catalogue.

The service is intentionally small. It exposes liveness and readiness
separately (readiness depends on PostgreSQL, liveness does not), and a few
bounded workload endpoints used by the fault scripts to create CPU/memory
pressure without editing manifests.

Everything here runs in the disposable lab only (namespace ``aiops-test``).
Fault endpoints can be disabled with ``ENABLE_FAULT_ENDPOINTS=false``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

SERVICE_NAME = os.getenv("SERVICE_NAME", "shop-demo")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")

DB_HOST = os.getenv("DB_HOST", "shop-demo-db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "shop")
DB_USER = os.getenv("DB_USER", "shop")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "2"))

FAULT_ENDPOINTS = os.getenv("ENABLE_FAULT_ENDPOINTS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

_SECRET_KEY = re.compile(r"(?i)(pass(word|wd)?|secret|token|authorization|dsn|credential)")


class JsonFormatter(logging.Formatter):
    """One JSON object per line; redacts credential-looking field names."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": SERVICE_NAME,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update({key: _redact(key, value) for key, value in fields.items()})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(payload, separators=(",", ":"), default=str)


def _redact(key: str, value: Any) -> Any:
    return "[REDACTED]" if _SECRET_KEY.search(key) else value


logger = logging.getLogger("shop-demo")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger.addHandler(_handler)
logger.propagate = False


def log_event(level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"fields": fields})


def check_database() -> tuple[bool, str]:
    """Return (reachable, short_state). Never log the DSN or the exception text."""
    try:
        with psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=DB_CONNECT_TIMEOUT,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return True, "up"
    except Exception as exc:  # noqa: BLE001 - readiness must never crash the process
        return False, type(exc).__name__


@asynccontextmanager
async def lifespan(_: FastAPI) -> Iterator[None]:
    log_event(logging.INFO, "service_started", version=SERVICE_VERSION, db_host=DB_HOST)
    yield
    log_event(logging.INFO, "service_stopped")


app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION, lifespan=lifespan)


@app.get("/")
def index() -> dict[str, Any]:
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "endpoints": [
            "/health/live",
            "/health/ready",
            "/work/cpu",
            "/work/memory",
            "/work/fail",
        ],
    }


@app.get("/health/live")
def live() -> dict[str, str]:
    """Process liveness only. A database outage must not restart the pods."""
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/health/ready")
def ready() -> JSONResponse:
    reachable, state = check_database()
    body = {"status": "ready" if reachable else "not_ready", "database": state}
    return JSONResponse(status_code=200 if reachable else 503, content=body)


def _burn_cpu(deadline: float) -> None:
    value = 0
    while time.monotonic() < deadline:
        value = (value + 1) % 1_000_003


@app.get("/work/cpu")
def work_cpu(
    seconds: float = Query(10.0, ge=0.1, le=60.0),
    workers: int = Query(1, ge=1, le=4),
) -> dict[str, Any]:
    """Bounded CPU pressure: one busy Python thread per worker."""
    deadline = time.monotonic() + seconds
    threads = [
        threading.Thread(target=_burn_cpu, args=(deadline,), daemon=True) for _ in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    log_event(logging.INFO, "workload_finished", workload="cpu", seconds=seconds, workers=workers)
    return {"workload": "cpu", "seconds": seconds, "workers": workers}


@app.get("/work/memory")
def work_memory(
    mb: int = Query(64, ge=1, le=512),
    seconds: float = Query(10.0, ge=0.1, le=60.0),
) -> dict[str, Any]:
    """Bounded memory pressure: touch every page, hold it, then release."""
    block = bytearray(mb * 1024 * 1024)
    for offset in range(0, len(block), 4096):
        block[offset] = 1
    time.sleep(seconds)
    log_event(logging.INFO, "workload_finished", workload="memory", mb=mb, seconds=seconds)
    return {"workload": "memory", "mb": mb, "seconds": seconds}


@app.get("/work/fail")
def work_fail(mode: str = Query("error", pattern="^(error|crash)$")) -> dict[str, Any]:
    """Break the service on purpose (F08): return 500 or exit the process."""
    if not FAULT_ENDPOINTS:
        raise HTTPException(status_code=404, detail="fault endpoints disabled")
    if mode == "error":
        log_event(logging.WARNING, "injected_failure", mode=mode)
        raise HTTPException(status_code=500, detail="injected application error")
    log_event(logging.WARNING, "injected_failure", mode=mode)
    threading.Timer(0.2, lambda: os._exit(1)).start()
    return {"workload": "fail", "mode": "crash", "exit_in_seconds": 0.2}
