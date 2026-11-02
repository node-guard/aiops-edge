"""FastAPI application for the central control plane (S1-A1 skeleton).

Only health endpoints live here for now. Operator routes land under ``/api/v1``
in S3/S6 and edge routes under ``/edge/v1`` in S5; both are tenant-scoped and
derive identity from the session or the mTLS certificate, never from the body.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from aiops.central.config import Settings
from aiops.central.db.engine import DependencyCheck, check_database, create_db_engine
from aiops.common.time import utcnow

logger = logging.getLogger("aiops.central.api")


def get_engine(request: Request) -> Engine:
    """Dependency so tests and future routes can share one engine per process."""
    engine: Engine = request.app.state.engine
    return engine


EngineDep = Annotated[Engine, Depends(get_engine)]


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, "ts": utcnow().isoformat(), **fields}))


def _serialize(check: DependencyCheck) -> dict[str, Any]:
    return {
        "status": "ok" if check.ok else "error",
        "latency_ms": check.latency_ms,
        "detail": check.detail,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory. ``settings`` is injectable for tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or Settings.from_env()
        engine = create_db_engine(resolved.database_url)
        app.state.settings = resolved
        app.state.engine = engine
        _log("api_started", app_env=resolved.app_env)
        try:
            yield
        finally:
            engine.dispose()
            _log("api_stopped")

    app = FastAPI(title="aiops-edge central API", version="0.1.0", lifespan=lifespan)

    @app.get("/health/live", tags=["health"], summary="Process liveness")
    def live() -> dict[str, str]:
        """Returns 200 as long as the process is up; never touches dependencies."""
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"], summary="Traffic readiness")
    def ready(engine: EngineDep) -> JSONResponse:
        """Returns 200 only when PostgreSQL answers; 503 otherwise."""
        check = check_database(engine)
        payload = {
            "status": "ready" if check.ok else "not_ready",
            "checks": {check.name: "ok" if check.ok else check.detail},
            "checked_at": utcnow().isoformat(),
        }
        return JSONResponse(status_code=200 if check.ok else 503, content=payload)

    @app.get("/health/dependencies", tags=["health"], summary="Dependency detail")
    def dependencies(engine: EngineDep) -> dict[str, Any]:
        """Per-dependency status and latency, for operators and the lab."""
        check = check_database(engine)
        return {
            "checked_at": utcnow().isoformat(),
            "dependencies": {check.name: _serialize(check)},
        }

    return app


app = create_app()
