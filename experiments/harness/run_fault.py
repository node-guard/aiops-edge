"""Fault injection harness v0 (S2-B2).

Runs fault F01 (CPU saturation) or F02 (memory pressure) against the disposable
lab, refuses anything that is not the `aiops-lab` cluster and the `aiops-test`
namespace, writes a schema-valid `meta.json` plus a labelled `window.json`, and
appends one row to `experiments/runs/index.parquet`.

The injector is the `shop-demo` workload endpoint (`/work/cpu`, `/work/memory`)
because it is bounded, already deployed and does not need extra privileges. The
fault matrix names `stress-ng`; the effect (CPU burn / touched memory pages) is
the same and the deviation is recorded in `experiments/harness/README.md`.

Usage:
    uv run python experiments/harness/run_fault.py F01 --seconds 60 --workers 2
    uv run python experiments/harness/run_fault.py F02 --seconds 60 --mb 128
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "run-meta.v1.schema.json"
RUNS_DIR = ROOT / "experiments" / "runs"
INDEX_PATH = RUNS_DIR / "index.parquet"
DEFAULT_KUBECONFIG = ROOT / "deploy" / "lab" / ".state" / "kubeconfig"

ALLOWED_CONTEXT = "aiops-lab"
ALLOWED_NAMESPACE = "aiops-test"
DEFAULT_EXPECTED_SERVER = os.getenv("AIOPS_LAB_SERVER", "https://192.168.100.10:6443")
TARGET_SERVICE = "shop-demo"
HARNESS_VERSION = "run_fault.py/0.1"

# F02 must leave the container room to keep serving traffic and to avoid the
# OOM killer. The app limit is 256Mi today; the default injection is 128 MiB,
# which is half the limit and well below the ceiling.
DEFAULT_MEMORY_MB = 128
MEMORY_HEADROOM_MB = 64

_MEMORY_UNITS_MB: dict[str, float] = {
    "Ki": 1024 / 1024**2,
    "Mi": 1.0,
    "Gi": 1024.0,
    "Ti": 1024.0**2,
    "K": 1000 / 1024**2,
    "M": 1000**2 / 1024**2,
    "G": 1000**3 / 1024**2,
    "T": 1000**4 / 1024**2,
}
_MEMORY_QUANTITY = re.compile(r"^(?P<number>\d+(?:\.\d+)?)(?P<unit>Ki|Mi|Gi|Ti|K|M|G|T)?$")

INDEX_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("fault_id", pa.string()),
        ("target", pa.string()),
        ("t_injection", pa.string()),
        ("t_end", pa.string()),
        ("duration_seconds", pa.float64()),
        ("valid", pa.bool_()),
        ("config_hash", pa.string()),
        ("meta_path", pa.string()),
    ]
)


class HarnessError(RuntimeError):
    """A guard, kubectl or schema failure; no run is written."""


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_run_id(fault_id: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{fault_id}-{uuid.uuid4().hex[:6]}"


def check_lab_identity(
    context: str,
    server: str,
    namespace: str,
    expected_server: str = DEFAULT_EXPECTED_SERVER,
) -> None:
    """Fail closed unless this is exactly the disposable lab."""
    if context != ALLOWED_CONTEXT:
        raise HarnessError(f"refusing: context {context!r} is not {ALLOWED_CONTEXT!r}")
    if server.rstrip("/") != expected_server.rstrip("/"):
        raise HarnessError(
            f"refusing: context {ALLOWED_CONTEXT!r} points at {server!r}, not {expected_server!r}"
        )
    if namespace != ALLOWED_NAMESPACE:
        raise HarnessError(f"refusing: namespace {namespace!r} is not {ALLOWED_NAMESPACE!r}")


def parse_memory_mb(quantity: str) -> int:
    """Convert a Kubernetes memory quantity (``256Mi``) to whole MiB.

    Fails closed: an unparsable or unitless quantity is rejected rather than
    guessed. A bare number is a byte count in Kubernetes and converts to 0 MiB.
    """
    match = _MEMORY_QUANTITY.fullmatch(quantity.strip())
    if match is None:
        raise HarnessError(f"cannot parse memory quantity {quantity!r}")
    amount = float(match.group("number"))
    unit = match.group("unit") or ""
    if unit:
        mebibytes = amount * _MEMORY_UNITS_MB[unit]
    else:
        mebibytes = amount / 1024**2
    return int(mebibytes)


def validate_parameters(
    fault_id: str,
    *,
    seconds: int,
    workers: int | None = None,
    mb: int | None = None,
    memory_limit_mb: int | None = None,
) -> dict[str, int]:
    """Return the effective parameters, rejecting anything out of bounds.

    F02 must also fit inside the target container's memory limit. The limit is
    read from the live deployment and passed in, so the guard fails closed
    instead of trusting a constant that could drift from the manifest.
    """
    if not 1 <= seconds <= 60:
        raise HarnessError("seconds must be between 1 and 60")
    if fault_id == "F01":
        if workers is None or not 1 <= workers <= 4:
            raise HarnessError("F01 workers must be between 1 and 4")
        return {"seconds": seconds, "workers": workers}
    if fault_id == "F02":
        if mb is None or not 1 <= mb <= 512:
            raise HarnessError("F02 mb must be between 1 and 512")
        if memory_limit_mb is None:
            raise HarnessError("F02 needs the container memory limit; refusing to inject")
        ceiling = memory_limit_mb - MEMORY_HEADROOM_MB
        if mb > ceiling:
            raise HarnessError(
                f"F02 mb={mb} exceeds the safe ceiling {ceiling} MiB "
                f"(limit {memory_limit_mb} MiB minus {MEMORY_HEADROOM_MB} MiB headroom)"
            )
        return {"seconds": seconds, "mb": mb}
    raise HarnessError(f"unsupported fault id {fault_id!r}; expected F01 or F02")


def deployment_memory_limit_mb() -> int:
    """Read the shop-demo container limit from the lab and convert it to MiB."""
    quantity = kubectl(
        "-n",
        ALLOWED_NAMESPACE,
        "get",
        "deployment",
        TARGET_SERVICE,
        "-o",
        "jsonpath={.spec.template.spec.containers[0].resources.limits.memory}",
    )
    if not quantity:
        raise HarnessError(f"{TARGET_SERVICE} has no memory limit; refusing F02 (fail closed)")
    return parse_memory_mb(quantity)


def config_hash(
    *,
    fault_id: str,
    target: str,
    params: dict[str, int],
    component_versions: dict[str, str],
) -> str:
    payload = {
        "fault_id": fault_id,
        "target": target,
        "params": params,
        "component_versions": component_versions,
        "harness": HARNESS_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def build_meta(
    *,
    run_id: str,
    fault_id: str,
    target: str,
    t_injection: str,
    config_hash_value: str,
    component_versions: dict[str, str],
    valid: bool,
    invalid_reason: str | None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "fault_id": fault_id,
        "target": target,
        "t_injection": t_injection,
        "t_impact": None,
        "t_detection": None,
        "t_verified_recovery": None,
        "variant": "harness-v0",
        "config_hash": config_hash_value,
        "component_versions": component_versions,
        "valid": valid,
        "invalid_reason": invalid_reason,
    }


def validate_meta(meta: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(meta)


def append_index(path: Path, row: dict[str, Any]) -> None:
    """Append one row atomically; the file is small and single-writer."""
    new_table = pa.Table.from_pylist([row], schema=INDEX_SCHEMA)
    if path.exists():
        new_table = pa.concat_tables([pq.read_table(path), new_table])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    pq.write_table(new_table, temporary)
    temporary.replace(path)


def kubectl(*args: str) -> str:
    executable = shutil.which("kubectl")
    if executable is None:
        raise HarnessError("kubectl is not installed")
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable, no shell
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"kubectl {' '.join(args)} timed out after 30s; is the lab up?") from exc
    except OSError as exc:
        raise HarnessError(f"cannot run kubectl: {exc}") from exc
    if result.returncode != 0:
        raise HarnessError(
            f"kubectl {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def git_commit() -> str:
    executable = shutil.which("git")
    if executable is None:
        return "unknown"
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable, no shell
            [executable, "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError:
        return "unknown"
    return result.stdout.strip() or "unknown"


def guard_lab(namespace: str) -> None:
    os.environ.setdefault("KUBECONFIG", str(DEFAULT_KUBECONFIG))
    check_lab_identity(
        context=kubectl("config", "current-context"),
        server=kubectl(
            "config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}"
        ),
        namespace=namespace,
    )


def resolve_target() -> tuple[str, dict[str, str]]:
    """Return (base URL, component versions) for the shop-demo service."""
    available = kubectl(
        "-n",
        ALLOWED_NAMESPACE,
        "get",
        "deployment",
        TARGET_SERVICE,
        "-o",
        "jsonpath={.status.availableReplicas}",
    )
    if not available or int(available) < 1:
        raise HarnessError(f"{TARGET_SERVICE} has no available replica in {ALLOWED_NAMESPACE}")

    server = kubectl("config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}")
    host = urlparse(server).hostname
    if not host:
        raise HarnessError(f"cannot parse the API server host from {server!r}")

    node_port = kubectl(
        "-n",
        ALLOWED_NAMESPACE,
        "get",
        "service",
        TARGET_SERVICE,
        "-o",
        "jsonpath={.spec.ports[0].nodePort}",
    )
    if not node_port:
        raise HarnessError(f"service {TARGET_SERVICE} has no NodePort")

    image = kubectl(
        "-n",
        ALLOWED_NAMESPACE,
        "get",
        "deployment",
        TARGET_SERVICE,
        "-o",
        "jsonpath={.spec.template.spec.containers[0].image}",
    )
    k3s = (
        kubectl("get", "nodes", "-o", "jsonpath={.items[0].status.nodeInfo.kubeletVersion}")
        or "unknown"
    )

    versions = {
        "k3s": k3s,
        "shop_demo": image or "unknown",
        "harness_commit": git_commit(),
    }
    return f"http://{host}:{node_port}", versions


def precheck(base_url: str) -> None:
    try:
        response = httpx.get(f"{base_url}/health/ready", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HarnessError(f"{TARGET_SERVICE} is not ready, refusing to inject: {exc}") from exc


def inject(
    base_url: str, fault_id: str, params: dict[str, int]
) -> tuple[str, str, int, str | None]:
    """Call the bounded workload endpoint; return start, end, status, error."""
    path = "/work/cpu" if fault_id == "F01" else "/work/memory"
    started = utcnow_iso()
    try:
        response = httpx.get(
            f"{base_url}{path}",
            params=params,
            timeout=params["seconds"] + 30,
        )
        response.raise_for_status()
        status, error = response.status_code, None
    except httpx.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 0)
        error = f"{type(exc).__name__}: {exc}"
    ended = utcnow_iso()
    return started, ended, status, error


def write_run(
    *,
    run_id: str,
    fault_id: str,
    params: dict[str, int],
    target: str,
    started: str,
    ended: str,
    status: int,
    error: str | None,
    versions: dict[str, str],
) -> Path:
    valid = error is None and status == 200
    invalid_reason = None if valid else (error or f"unexpected HTTP status {status}")
    digest = config_hash(
        fault_id=fault_id,
        target=target,
        params=params,
        component_versions=versions,
    )
    meta = build_meta(
        run_id=run_id,
        fault_id=fault_id,
        target=target,
        t_injection=started,
        config_hash_value=digest,
        component_versions=versions,
        valid=valid,
        invalid_reason=invalid_reason,
    )
    validate_meta(meta)

    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    meta_path = run_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    (run_dir / "window.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "fault_id": fault_id,
                "params": params,
                "t_start": started,
                "t_end": ended,
                "duration_seconds": _duration_seconds(started, ended),
                "http_status": status,
                "error": error,
            },
            indent=2,
        )
        + "\n"
    )

    append_index(
        INDEX_PATH,
        {
            "run_id": run_id,
            "fault_id": fault_id,
            "target": target,
            "t_injection": started,
            "t_end": ended,
            "duration_seconds": _duration_seconds(started, ended),
            "valid": valid,
            "config_hash": digest,
            "meta_path": str(meta_path.relative_to(ROOT)),
        },
    )
    return meta_path


def _duration_seconds(started: str, ended: str) -> float:
    start = datetime.fromisoformat(started.replace("Z", "+00:00"))
    end = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    return round((end - start).total_seconds(), 3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fault F01 or F02 in the disposable lab.")
    parser.add_argument("fault_id", choices=["F01", "F02"])
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--workers", type=int, default=2, help="F01 only")
    parser.add_argument("--mb", type=int, default=DEFAULT_MEMORY_MB, help="F02 only")
    parser.add_argument("--namespace", default=ALLOWED_NAMESPACE)
    args = parser.parse_args(argv)

    try:
        guard_lab(args.namespace)
        limit_mb = deployment_memory_limit_mb() if args.fault_id == "F02" else None
        params = validate_parameters(
            args.fault_id,
            seconds=args.seconds,
            workers=args.workers,
            mb=args.mb,
            memory_limit_mb=limit_mb,
        )
        base_url, versions = resolve_target()
        precheck(base_url)
        started, ended, status, error = inject(base_url, args.fault_id, params)
        run_id = new_run_id(args.fault_id)
        meta_path = write_run(
            run_id=run_id,
            fault_id=args.fault_id,
            params=params,
            target=f"{ALLOWED_NAMESPACE}/{TARGET_SERVICE}",
            started=started,
            ended=ended,
            status=status,
            error=error,
            versions=versions,
        )
    except HarnessError as exc:
        print(f"[run_fault] ERROR: {exc}", file=sys.stderr)
        return 2

    valid = error is None and status == 200
    print(
        json.dumps(
            {
                "run_id": run_id,
                "fault_id": args.fault_id,
                "params": params,
                "t_injection": started,
                "t_end": ended,
                "duration_seconds": _duration_seconds(started, ended),
                "http_status": status,
                "valid": valid,
                "invalid_reason": error,
                "meta": str(meta_path.relative_to(ROOT)),
                "index": str(INDEX_PATH.relative_to(ROOT)),
            }
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
