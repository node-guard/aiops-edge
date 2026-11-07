"""Checks for the Locust healthy-load profiles (S2-B3).

The profiles are pure data in ``experiments/load/profiles.py``, so these tests
do not import Locust or gevent; the locustfile is checked statically.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOAD = ROOT / "experiments" / "load"
PROFILES_FILE = LOAD / "profiles.py"
LOCUSTFILE = LOAD / "locustfile.py"


def load_profiles():
    spec = importlib.util.spec_from_file_location("load_profiles", PROFILES_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_profiles()


def test_profiles_are_bounded_and_well_formed():
    assert set(MODULE.PROFILES) == {"smoke", "standard"}
    for name, stages in MODULE.PROFILES.items():
        assert stages, name
        stage_names = [stage.name for stage in stages]
        assert len(stage_names) == len(set(stage_names)), name
        for stage in stages:
            assert 0 < stage.users <= MODULE.MAX_USERS, (name, stage)
            assert 0 < stage.spawn_rate <= stage.users, (name, stage)
            assert 0 < stage.duration_seconds, (name, stage)


def test_standard_profile_contains_real_variation():
    stages = MODULE.PROFILES["standard"]
    assert [stage.name for stage in stages] == [
        "warmup",
        "steady",
        "burst",
        "recovery",
    ]
    assert len({stage.users for stage in stages}) >= 3
    assert max(stage.users for stage in stages) == 25
    assert sum(stage.duration_seconds for stage in stages) == 21 * 60


def test_smoke_profile_is_short_and_small():
    stages = MODULE.PROFILES["smoke"]
    assert sum(stage.duration_seconds for stage in stages) <= 120
    assert max(stage.users for stage in stages) <= 5


def test_profile_selection_fails_closed(monkeypatch):
    monkeypatch.setenv("LOAD_PROFILE", "smoke")
    assert MODULE.active_profile() == "smoke"
    monkeypatch.setenv("LOAD_PROFILE", "SMOKE")
    assert MODULE.active_profile() == "smoke"
    monkeypatch.setenv("LOAD_PROFILE", "not-a-profile")
    with pytest.raises(RuntimeError, match="unknown LOAD_PROFILE"):
        MODULE.active_profile()


def test_generator_never_calls_fault_hooks_or_writes():
    tree = ast.parse(LOCUSTFILE.read_text())
    urls = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("/")
    }
    assert urls
    assert all(not url.startswith("/work") for url in urls), urls

    methods = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "client"
    }
    assert methods == {"get"}, methods
    assert "from profiles import" in LOCUSTFILE.read_text()


def test_generator_targets_the_lab_by_default():
    assert MODULE.DEFAULT_HOST.startswith("http://192.168.100.")
