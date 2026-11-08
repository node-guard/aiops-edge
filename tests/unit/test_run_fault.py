"""Unit checks for the fault harness (S2-B2). No cluster is required."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "experiments" / "harness" / "run_fault.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_fault", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_harness()

VERSIONS = {"k3s": "v1.31.4+k3s1", "shop_demo": "shop-demo@sha256:" + "a" * 64}


def valid_meta(**overrides):
    values = {
        "run_id": "20261107T080000Z-F01-abcdef",
        "fault_id": "F01",
        "target": "aiops-test/shop-demo",
        "t_injection": "2026-11-07T08:00:00Z",
        "config_hash_value": "sha256:" + "b" * 64,
        "component_versions": VERSIONS,
        "valid": True,
        "invalid_reason": None,
    }
    values.update(overrides)
    return MODULE.build_meta(**values)


def test_guard_accepts_only_the_lab():
    MODULE.check_lab_identity("aiops-lab", "https://192.168.100.10:6443", "aiops-test")

    with pytest.raises(MODULE.HarnessError, match="context"):
        MODULE.check_lab_identity("prod", "https://192.168.100.10:6443", "aiops-test")
    with pytest.raises(MODULE.HarnessError, match="points at"):
        MODULE.check_lab_identity("aiops-lab", "https://10.0.0.1:6443", "aiops-test")
    with pytest.raises(MODULE.HarnessError, match="namespace"):
        MODULE.check_lab_identity("aiops-lab", "https://192.168.100.10:6443", "kube-system")


def test_parameter_bounds():
    assert MODULE.validate_parameters("F01", seconds=60, workers=4) == {
        "seconds": 60,
        "workers": 4,
    }
    assert MODULE.validate_parameters("F02", seconds=1, mb=128, memory_limit_mb=256) == {
        "seconds": 1,
        "mb": 128,
    }
    assert MODULE.validate_parameters("F02", seconds=10, mb=192, memory_limit_mb=256) == {
        "seconds": 10,
        "mb": 192,
    }
    with pytest.raises(MODULE.HarnessError):
        MODULE.validate_parameters("F01", seconds=61, workers=1)
    with pytest.raises(MODULE.HarnessError):
        MODULE.validate_parameters("F01", seconds=10, workers=5)
    with pytest.raises(MODULE.HarnessError):
        MODULE.validate_parameters("F02", seconds=10, mb=0, memory_limit_mb=256)
    with pytest.raises(MODULE.HarnessError):
        MODULE.validate_parameters("F03", seconds=10)


def test_f02_never_exceeds_the_container_limit():
    # 256Mi limit, 64 MiB headroom: the ceiling is 192 MiB.
    with pytest.raises(MODULE.HarnessError, match="safe ceiling 192"):
        MODULE.validate_parameters("F02", seconds=10, mb=193, memory_limit_mb=256)
    with pytest.raises(MODULE.HarnessError, match="safe ceiling"):
        MODULE.validate_parameters("F02", seconds=10, mb=512, memory_limit_mb=256)
    # A limit read from a different manifest changes the ceiling accordingly.
    with pytest.raises(MODULE.HarnessError, match="safe ceiling 0"):
        MODULE.validate_parameters("F02", seconds=10, mb=1, memory_limit_mb=64)


def test_f02_fails_closed_without_a_known_limit():
    with pytest.raises(MODULE.HarnessError, match="memory limit"):
        MODULE.validate_parameters("F02", seconds=10, mb=128)


def test_memory_quantity_parsing():
    assert MODULE.parse_memory_mb("256Mi") == 256
    assert MODULE.parse_memory_mb("1Gi") == 1024
    assert MODULE.parse_memory_mb("512M") == 488
    assert MODULE.parse_memory_mb("134217728") == 128
    assert MODULE.parse_memory_mb(" 256Mi ") == 256
    with pytest.raises(MODULE.HarnessError, match="cannot parse"):
        MODULE.parse_memory_mb("256MB")
    with pytest.raises(MODULE.HarnessError, match="cannot parse"):
        MODULE.parse_memory_mb("lots")


def test_kubectl_timeout_fails_closed(monkeypatch):
    monkeypatch.setattr(MODULE.shutil, "which", lambda _: "/usr/bin/kubectl")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="kubectl", timeout=30)

    monkeypatch.setattr(MODULE.subprocess, "run", timeout)
    with pytest.raises(MODULE.HarnessError, match="timed out after 30s"):
        MODULE.kubectl("get", "pods")


def test_valid_meta_passes_the_frozen_schema():
    MODULE.validate_meta(valid_meta())


def test_invalid_run_must_state_a_reason():
    meta = valid_meta(valid=False, invalid_reason=None)
    with pytest.raises(jsonschema.ValidationError):
        MODULE.validate_meta(meta)

    MODULE.validate_meta(valid_meta(valid=False, invalid_reason="injection failed"))


def test_schema_rejects_unknown_fields():
    meta = valid_meta()
    meta["extra"] = "not allowed"
    with pytest.raises(jsonschema.ValidationError):
        MODULE.validate_meta(meta)


def test_config_hash_is_stable_and_sensitive_to_parameters():
    first = MODULE.config_hash(
        fault_id="F01",
        target="aiops-test/shop-demo",
        params={"seconds": 60, "workers": 2},
        component_versions=VERSIONS,
    )
    second = MODULE.config_hash(
        fault_id="F01",
        target="aiops-test/shop-demo",
        params={"seconds": 60, "workers": 2},
        component_versions=VERSIONS,
    )
    changed = MODULE.config_hash(
        fault_id="F01",
        target="aiops-test/shop-demo",
        params={"seconds": 60, "workers": 4},
        component_versions=VERSIONS,
    )
    assert first == second
    assert first != changed
    assert re.fullmatch(r"sha256:[a-f0-9]{64}", first)


def test_run_id_is_unique_and_readable():
    first = MODULE.new_run_id("F01")
    second = MODULE.new_run_id("F01")
    assert first != second
    assert re.fullmatch(r"\d{8}T\d{6}Z-F01-[0-9a-f]{6}", first)


def test_index_append_creates_and_appends(tmp_path):
    path = tmp_path / "index.parquet"
    row = {
        "run_id": "20261107T080000Z-F01-abcdef",
        "fault_id": "F01",
        "target": "aiops-test/shop-demo",
        "t_injection": "2026-11-07T08:00:00Z",
        "t_end": "2026-11-07T08:01:00Z",
        "duration_seconds": 60.0,
        "valid": True,
        "config_hash": "sha256:" + "b" * 64,
        "meta_path": "experiments/runs/run/meta.json",
    }
    MODULE.append_index(path, row)
    MODULE.append_index(path, {**row, "run_id": "second"})

    table = pq.read_table(path)
    assert table.num_rows == 2
    assert table.column_names == [
        "run_id",
        "fault_id",
        "target",
        "t_injection",
        "t_end",
        "duration_seconds",
        "valid",
        "config_hash",
        "meta_path",
    ]
    assert table.column("run_id").to_pylist() == [row["run_id"], "second"]


def test_meta_file_is_plain_json_and_round_trips(tmp_path):
    meta = valid_meta()
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(meta, indent=2) + "\n")
    assert json.loads(path.read_text()) == meta
