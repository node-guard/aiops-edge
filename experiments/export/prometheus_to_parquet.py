"""Export Prometheus series to a Parquet dataset with units (S2-B5).

The output is raw samples in long format: one row per observed sample. Missing
samples are *not* filled with zeros or interpolated; a gap in Prometheus is a
gap in the Parquet file, and the manifest reports the coverage per query so the
feature pipeline (S4-B1) can decide what to do with it.

Usage:
    kubectl -n aiops-system port-forward svc/edge-stack-prometheus 9090:9090 &
    make export START=2026-11-09T07:00:00Z END=2026-11-09T08:00:00Z

Each query in ``queries.yaml`` declares a name, a PromQL expression and a unit.
The metric name in the output is the config ``name``, not ``__name__``: several
queries are expressions and have no single source metric.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "experiments" / "export" / "queries.yaml"
DEFAULT_URL = "http://127.0.0.1:9090"
EXPORT_SCHEMA = "prometheus-export.v1"
EXPORTER_VERSION = "prometheus_to_parquet.py/0.1"
MAX_STEPS = 10_000
MIN_STEP_SECONDS = 10
MAX_STEP_SECONDS = 3600

# Controlled vocabulary. A typo in ``queries.yaml`` would otherwise become a
# silently wrong feature column in S4; reject it here instead.
ALLOWED_UNITS = frozenset(
    {
        "bool",
        "bytes",
        "bytes_per_second",
        "count",
        "load_average",
        "ratio",
        "seconds",
    }
)

PARQUET_SCHEMA = pa.schema(
    [
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("metric", pa.string()),
        ("unit", pa.string()),
        ("series_id", pa.string()),
        ("labels", pa.string()),
        ("value", pa.float64()),
        ("site", pa.string()),
    ]
)


class ExportError(RuntimeError):
    """A configuration, network or data problem; no file is written."""


@dataclass(frozen=True, slots=True)
class QuerySpec:
    name: str
    query: str
    unit: str
    description: str = ""
    allow_empty: bool = False


@dataclass(frozen=True, slots=True)
class ExportRange:
    start: datetime
    end: datetime
    step_seconds: int

    @property
    def steps(self) -> int:
        return int((self.end - self.start).total_seconds() // self.step_seconds) + 1


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExportError(f"invalid RFC 3339 timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise ExportError(f"timestamp {value!r} must include an offset")
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_range(start: datetime, end: datetime, step_seconds: int) -> ExportRange:
    if end <= start:
        raise ExportError("--end must be after --start")
    if not MIN_STEP_SECONDS <= step_seconds <= MAX_STEP_SECONDS:
        raise ExportError(
            f"--step must be between {MIN_STEP_SECONDS} and {MAX_STEP_SECONDS} seconds"
        )
    window = ExportRange(start=start, end=end, step_seconds=step_seconds)
    if window.steps > MAX_STEPS:
        raise ExportError(
            f"range needs {window.steps} steps, above the {MAX_STEPS} limit; "
            "increase --step or shorten the window"
        )
    return window


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    return "" if value is None else str(value).strip()


def load_queries(path: Path) -> list[QuerySpec]:
    try:
        document = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ExportError(f"cannot read query config {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("queries"), list):
        raise ExportError(f"{path} must contain a 'queries' list")

    queries: list[QuerySpec] = []
    seen: set[str] = set()
    for index, item in enumerate(document["queries"]):
        if not isinstance(item, dict):
            raise ExportError(f"query #{index} must be a mapping")
        name = _text(item, "name")
        expression = _text(item, "query")
        unit = _text(item, "unit")
        if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
            raise ExportError(f"query #{index} has an invalid name {name!r}")
        if name in seen:
            raise ExportError(f"duplicate query name {name!r}")
        if not expression:
            raise ExportError(f"query {name!r} has an empty expression")
        if not unit:
            raise ExportError(f"query {name!r} has no unit")
        if unit not in ALLOWED_UNITS:
            raise ExportError(
                f"query {name!r} has unit {unit!r}; allowed units are "
                + ", ".join(sorted(ALLOWED_UNITS))
            )
        seen.add(name)
        allow_empty = item.get("allow_empty", False)
        if not isinstance(allow_empty, bool):
            raise ExportError(f"query {name!r} has non-boolean allow_empty {allow_empty!r}")
        queries.append(
            QuerySpec(
                name=name,
                query=expression,
                unit=unit,
                description=_text(item, "description"),
                allow_empty=allow_empty,
            )
        )
    if not queries:
        raise ExportError(f"{path} has no queries")
    return queries


def safe_url(url: str) -> str:
    """Drop userinfo so a credential never reaches the manifest or logs."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def fetch_matrix(
    client: httpx.Client,
    base_url: str,
    query: QuerySpec,
    window: ExportRange,
) -> list[dict[str, Any]]:
    try:
        response = client.get(
            f"{base_url.rstrip('/')}/api/v1/query_range",
            params={
                "query": query.query,
                "start": iso(window.start),
                "end": iso(window.end),
                "step": window.step_seconds,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        raise ExportError(
            f"Prometheus timed out on query {query.name!r}; is it reachable?"
        ) from exc
    except httpx.HTTPError as exc:
        detail = str(exc).replace(base_url, safe_url(base_url))
        raise ExportError(f"Prometheus request failed on {query.name!r}: {detail}") from exc
    except ValueError as exc:
        raise ExportError(f"Prometheus returned non-JSON for {query.name!r}") from exc

    if payload.get("status") != "success":
        raise ExportError(f"Prometheus error on {query.name!r}: {payload.get('error', 'unknown')}")
    data = payload.get("data", {})
    if data.get("resultType") != "matrix":
        raise ExportError(
            f"query {query.name!r} returned {data.get('resultType')!r}, expected 'matrix'"
        )
    result = data.get("result", [])
    if not isinstance(result, list):
        raise ExportError(f"query {query.name!r} returned a malformed result")
    return result


def canonical_labels(labels: dict[str, str]) -> str:
    without_name = {key: value for key, value in labels.items() if key != "__name__"}
    return json.dumps(without_name, sort_keys=True, separators=(",", ":"))


def series_id(metric: str, labels: str) -> str:
    digest = hashlib.sha256(f"{metric}\n{labels}".encode()).hexdigest()
    return digest[:16]


def build_rows(
    metric: str,
    unit: str,
    site: str,
    result: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Flatten a matrix; return rows, non-finite count and series count.

    A series with missing timestamps produces fewer rows, never a filled value.
    Malformed samples are an error: a truncated float would silently corrupt a
    feature, so the whole export fails instead.
    """
    rows: list[dict[str, Any]] = []
    skipped_non_finite = 0
    for series in result:
        labels = canonical_labels(series.get("metric", {}))
        identifier = series_id(metric, labels)
        for raw_timestamp, raw_value in series.get("values", []):
            try:
                value = float(raw_value)
                timestamp = datetime.fromtimestamp(float(raw_timestamp), UTC)
            except (TypeError, ValueError) as exc:
                raise ExportError(
                    f"query {metric!r} returned a non-numeric sample {raw_value!r}"
                ) from exc
            if not math.isfinite(value):
                skipped_non_finite += 1
                continue
            rows.append(
                {
                    "timestamp": timestamp,
                    "metric": metric,
                    "unit": unit,
                    "series_id": identifier,
                    "labels": labels,
                    "value": value,
                    "site": site,
                }
            )
    return rows, skipped_non_finite, len(result)


def summarise(
    query: QuerySpec, rows: list[dict[str, Any]], series_count: int, expected_per_series: int
) -> dict[str, Any]:
    samples = len(rows)
    expected = series_count * expected_per_series
    per_series: dict[str, int] = {}
    for row in rows:
        per_series[row["series_id"]] = per_series.get(row["series_id"], 0) + 1
    return {
        "name": query.name,
        "unit": query.unit,
        "series": series_count,
        "samples": samples,
        "expected_samples": expected,
        "coverage": round(samples / expected, 4) if expected else None,
        "series_below_full_coverage": sum(
            1 for count in per_series.values() if count < expected_per_series
        ),
        "empty": series_count == 0,
    }


def write_parquet(rows: list[dict[str, Any]], path: Path, site: str) -> None:
    table = pa.Table.from_pylist(rows, schema=PARQUET_SCHEMA)
    table = table.sort_by(
        [
            ("metric", "ascending"),
            ("series_id", "ascending"),
            ("timestamp", "ascending"),
        ]
    )
    units = sorted({row["unit"] for row in rows})
    table = table.replace_schema_metadata(
        {
            b"export_schema": EXPORT_SCHEMA.encode(),
            b"site": site.encode(),
            b"units": json.dumps(units).encode(),
            b"no_zero_fill": b"true",
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        pq.write_table(table, temporary, compression="zstd")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def prometheus_version(client: httpx.Client, base_url: str) -> str:
    try:
        response = client.get(f"{base_url.rstrip('/')}/api/v1/status/buildinfo")
        response.raise_for_status()
        return str(response.json().get("data", {}).get("version", "unknown"))
    except (httpx.HTTPError, ValueError):
        return "unknown"


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


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _min_coverage(queries: list[dict[str, Any]]) -> float | None:
    values = [item["coverage"] for item in queries if item["coverage"] is not None]
    return min(values) if values else None


def export(
    *,
    url: str,
    window: ExportRange,
    queries: list[QuerySpec],
    config_path: Path,
    site: str,
    timeout: float,
    output_dir: Path | None = None,
    client: httpx.Client | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    skipped_non_finite = 0

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=timeout)
    assert client is not None
    try:
        version = prometheus_version(client, url)
        for query in queries:
            result = fetch_matrix(client, url, query, window)
            query_rows, skipped, series_count = build_rows(query.name, query.unit, site, result)
            if series_count == 0 and not query.allow_empty:
                raise ExportError(
                    f"query {query.name!r} returned no series; fix the selector or "
                    "set allow_empty: true if an empty result is expected"
                )
            rows.extend(query_rows)
            skipped_non_finite += skipped
            summaries.append(summarise(query, query_rows, series_count, window.steps))
    finally:
        if owns_client:
            client.close()

    if not rows:
        raise ExportError(
            "no samples returned; refusing to write an empty export (check selectors and range)"
        )

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if output_dir is None:
        output_dir = ROOT / "experiments" / "runs" / f"export-{stamp}-{uuid.uuid4().hex[:6]}"
    parquet_path = output_dir / "metrics.parquet"
    manifest_path = output_dir / "manifest.json"

    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    write_parquet(rows, parquet_path, site)

    manifest = {
        "schema": EXPORT_SCHEMA,
        "exporter": EXPORTER_VERSION,
        "generated_at": iso(datetime.now(UTC)),
        "site": site,
        "prometheus": {"url": safe_url(url), "version": version},
        "range": {
            "start": iso(window.start),
            "end": iso(window.end),
            "step_seconds": window.step_seconds,
            "steps": window.steps,
        },
        "config": {"path": _display_path(config_path), "sha256": config_sha},
        "parquet": parquet_path.name,
        "rows": len(rows),
        "skipped_non_finite": skipped_non_finite,
        "queries": summaries,
        "git_commit": git_commit(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return parquet_path, manifest_path, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export Prometheus series to Parquet with units and a coverage manifest."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Prometheus base URL")
    parser.add_argument("--start", required=True, help="RFC 3339 start (inclusive)")
    parser.add_argument("--end", required=True, help="RFC 3339 end (inclusive)")
    parser.add_argument("--step", type=int, default=30, help="step in seconds")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--site", default="lab")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="output directory (default: experiments/runs/export-<stamp>-<id>)",
    )
    args = parser.parse_args(argv)

    try:
        window = validate_range(parse_time(args.start), parse_time(args.end), args.step)
        queries = load_queries(args.config)
        parquet_path, manifest_path, manifest = export(
            url=args.url,
            window=window,
            queries=queries,
            config_path=args.config,
            site=args.site,
            timeout=args.timeout,
            output_dir=args.output_dir,
        )
    except ExportError as exc:
        print(f"[export] ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"[export] ERROR: cannot write output: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "parquet": _display_path(parquet_path),
                "manifest": _display_path(manifest_path),
                "rows": manifest["rows"],
                "queries": len(manifest["queries"]),
                "empty_queries": sum(1 for item in manifest["queries"] if item["empty"]),
                "min_coverage": _min_coverage(manifest["queries"]),
                "skipped_non_finite": manifest["skipped_non_finite"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
