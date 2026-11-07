"""Healthy-load profile definitions (S2-B3).

Kept free of Locust imports so unit tests can validate the profiles without
pulling gevent into pytest. ``locustfile.py`` consumes these definitions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# The lab NodePort. Override with --host or SHOP_DEMO_URL.
DEFAULT_HOST = os.getenv("SHOP_DEMO_URL", "http://192.168.100.10:30080")

# Safety ceiling: the worker has 2 vCPU / 2 GiB. Above this the traffic is no
# longer "healthy variation" and the run stops being a baseline.
MAX_USERS = 30


@dataclass(frozen=True)
class Stage:
    """One constant-load segment of a profile."""

    name: str
    duration_seconds: int
    users: int
    spawn_rate: float


# A standard cycle is 21 minutes: warm-up, steady, burst, recovery. Repeating
# the cycle gives the soak a daily rhythm without ever touching Prometheus.
PROFILES: dict[str, tuple[Stage, ...]] = {
    "smoke": (Stage("smoke", duration_seconds=60, users=3, spawn_rate=1),),
    "standard": (
        Stage("warmup", duration_seconds=60, users=5, spawn_rate=1),
        Stage("steady", duration_seconds=600, users=10, spawn_rate=2),
        Stage("burst", duration_seconds=180, users=25, spawn_rate=5),
        Stage("recovery", duration_seconds=420, users=8, spawn_rate=2),
    ),
}


def active_profile() -> str:
    """Return the requested profile name, failing closed on a typo."""
    name = os.getenv("LOAD_PROFILE", "standard").strip().lower()
    if name not in PROFILES:
        raise RuntimeError(
            f"unknown LOAD_PROFILE {name!r}; choose from {', '.join(sorted(PROFILES))}"
        )
    return name
