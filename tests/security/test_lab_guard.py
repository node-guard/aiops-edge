"""Security boundary: the lab context guard (S1-B1).

The guard must refuse every cluster that is not the disposable aiops-lab. A
stub kubectl keeps this test independent of a real cluster.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "deploy" / "lab" / "lib" / "lab-guard.sh"

STUB = """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "config" && "${2:-}" == "current-context" ]]; then
  printf '%s\\n' "${STUB_CONTEXT:-}"
  exit 0
fi
if [[ "${1:-}" == "config" && "${2:-}" == "view" ]]; then
  printf '%s\\n' "${STUB_SERVER:-}"
  exit 0
fi
exit 1
"""


def run_guard(tmp_path: Path, context: str, server: str, *args: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(STUB)
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "KUBECONFIG": str(tmp_path / "kubeconfig"),
        "STUB_CONTEXT": context,
        "STUB_SERVER": server,
    }
    return subprocess.run(
        ["bash", str(GUARD), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_guard_accepts_the_lab_context(tmp_path: Path):
    result = run_guard(tmp_path, "aiops-lab", "https://192.168.100.10:6443")
    assert result.returncode == 0, result.stderr
    assert "ok: context aiops-lab" in result.stdout


def test_guard_rejects_another_context(tmp_path: Path):
    result = run_guard(tmp_path, "prod-eu", "https://192.168.100.10:6443")
    assert result.returncode == 1
    assert "refusing" in result.stderr
    assert "prod-eu" in result.stderr


def test_guard_rejects_a_lab_named_context_pointing_elsewhere(tmp_path: Path):
    result = run_guard(tmp_path, "aiops-lab", "https://10.20.30.40:6443")
    assert result.returncode == 1
    assert "not the lab API" in result.stderr


def test_guard_rejects_missing_context(tmp_path: Path):
    result = run_guard(tmp_path, "", "https://192.168.100.10:6443")
    assert result.returncode == 1
    assert "<none>" in result.stderr


def test_guard_rejects_unknown_arguments(tmp_path: Path):
    result = run_guard(tmp_path, "aiops-lab", "https://192.168.100.10:6443", "--force")
    assert result.returncode == 2
