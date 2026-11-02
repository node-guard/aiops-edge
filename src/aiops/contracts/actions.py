"""Load the action catalogue and autonomy policy; helper to decide the level of an action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]


def load_yaml(rel: str) -> dict[str, Any]:
    data = yaml.safe_load((ROOT / rel).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{rel} must be a mapping")
    return data


def action_levels() -> dict[str, str]:
    cat = load_yaml("contracts/actions/actions.yaml")
    return {a["id"]: a["default_level"] for a in cat["actions"]}


def level_for_scale(current: int, new: int, max_replicas: int) -> str:
    """ACT-002: L1 only for scale-out by at most one replica, within max; otherwise L2."""
    if new > current and (new - current) <= 1 and new <= max_replicas:
        return "L1"
    return "L2"
