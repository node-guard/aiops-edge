"""Locust workload profiles for the shop-demo healthy baseline (S2-B3).

The generator exercises only read-only endpoints. The ``/work/*`` fault hooks
are deliberately excluded: they belong to the fault harness and would
contaminate the healthy-data soak with synthetic CPU/memory pressure.

Profiles are selected with ``LOAD_PROFILE`` (default ``standard``); the stage
definitions live in ``profiles.py`` and are documented in ``README.md``.
Run through ``experiments/load/run.sh`` or ``make load PROFILE=smoke``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from locust import HttpUser, LoadTestShape, between, task

# Locust runs this file by path, so make the sibling ``profiles`` module
# importable without turning experiments/ into a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from profiles import DEFAULT_HOST, PROFILES, active_profile  # noqa: E402


class HealthyVariationShape(LoadTestShape):
    """Piecewise-constant user count; returns None to stop the test."""

    stages = PROFILES[active_profile()]

    def tick(self) -> tuple[int, float] | None:
        run_time = self.get_run_time()
        elapsed = 0.0
        for stage in self.stages:
            if run_time < elapsed + stage.duration_seconds:
                return stage.users, stage.spawn_rate
            elapsed += stage.duration_seconds
        return None


class ShopUser(HttpUser):
    """A browser-like visitor plus the health probes monitoring would send."""

    host = DEFAULT_HOST
    wait_time = between(1, 3)

    @task(6)
    def browse(self) -> None:
        self.client.get("/", name="/")

    @task(3)
    def liveness(self) -> None:
        self.client.get("/health/live", name="/health/live")

    @task(2)
    def readiness(self) -> None:
        # Hits PostgreSQL, so it is slower than the other two. Keep the weight
        # low: a real visitor does not query the database on every page view.
        self.client.get("/health/ready", name="/health/ready")
