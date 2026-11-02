"""Central worker process skeleton (S1-A1).

The worker owns background work: ingestion follow-ups, notification fan-out and
remediation expiry in later sprints. For now it proves the process wiring: it
loads the same settings as the API, probes PostgreSQL on a fixed interval, and
shuts down cleanly on SIGTERM so ``docker compose down`` is not a 10 s timeout.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
from types import FrameType

from aiops.central.config import ConfigError, Settings
from aiops.central.db.engine import check_database, create_db_engine
from aiops.common.time import utcnow

logger = logging.getLogger("aiops.central.worker")
_shutdown = threading.Event()


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    _log("worker_signal", signal=signum)
    _shutdown.set()


def _log(event: str, **fields: object) -> None:
    logger.info(json.dumps({"event": event, "ts": utcnow().isoformat(), **fields}))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        logger.error(json.dumps({"event": "worker_exit", "reason": str(exc)}))
        return 2

    engine = create_db_engine(settings.database_url)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    _log("worker_started", app_env=settings.app_env, poll_seconds=settings.worker_poll_seconds)

    try:
        while not _shutdown.is_set():
            check = check_database(engine)
            _log(
                "worker_heartbeat",
                postgres="ok" if check.ok else "error",
                latency_ms=check.latency_ms,
            )
            _shutdown.wait(settings.worker_poll_seconds)
    finally:
        engine.dispose()

    _log("worker_stopped", clean=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
