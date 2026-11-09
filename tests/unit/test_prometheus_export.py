"""Unit checks for the Prometheus -> Parquet exporter (S2-B5).

No Prometheus and no cluster: HTTP is faked with ``httpx.MockTransport``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPORTER = ROOT / "experiments" / "export" / "prometheus_to_parquet.py"
DEFAULT_CONFIG = ROOT / "experiments" / "export" / "queries.yaml"


def load_exporter():
    spec = importlib.util.spec_from_file_location("prometheus_to_parquet", EXPORTER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_exporter()

BASE = datetime(2026, 11, 9, 7, 0, tzinfo=UTC)
T = [BASE.timestamp(), BASE.timestamp() + 30, BASE.timestamp() + 60]


def matrix(labels, values, *, name="source_metric"):
    return [{"metric": {"__name__": name, **labels}, "values": [[t, v] for t, v in values]}]


def buildinfo() -> httpx.Response:
    return httpx.Response(200, json={"status": "success", "data": {"version": "3.5.0"}})


def range_response(result) -> httpx.Response:
    return httpx.Response(
        200,
        json={"status": "success", "data": {"resultType": "matrix", "result": result}},
    )


def client_for(matrices: dict[str, list], handler=None) -> httpx.Client:
    def default_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/status/buildinfo":
            return buildinfo()
        if request.url.path == "/api/v1/query_range":
            query = request.url.params["query"]
            if query not in matrices:
                return httpx.Response(400, text=f"unexpected query {query}")
            return range_response(matrices[query])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler or default_handler))


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "queries.yaml"
    path.write_text(text)
    return path


VALID_CONFIG = """
queries:
  - name: node_memory_available_bytes
    query: node_memory_MemAvailable_bytes
    unit: bytes
  - name: node_cpu_busy_ratio
    query: 1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]))
    unit: ratio
"""


def run_export(tmp_path: Path, matrices: dict[str, list], **overrides):
    config = overrides.pop("config", None) or write_config(tmp_path, VALID_CONFIG)
    window = overrides.pop(
        "window",
        MODULE.ExportRange(start=BASE, end=BASE.replace(minute=1), step_seconds=30),
    )
    queries = overrides.pop("queries", None) or MODULE.load_queries(config)
    client = overrides.pop("client", None)
    if client is None:
        client = client_for(matrices)
    return MODULE.export(
        url=overrides.pop("url", "http://127.0.0.1:9090"),
        window=window,
        queries=queries,
        config_path=config,
        site=overrides.pop("site", "lab"),
        timeout=5.0,
        output_dir=overrides.pop("output_dir", tmp_path / "out"),
        client=client,
    )


# --- time and range guards -------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["2026-11-09T07:00:00Z", "2026-11-09T07:00:00+00:00", "2026-11-09T08:00:00+01:00"],
)
def test_parse_time_accepts_rfc3339_with_an_offset(value):
    parsed = MODULE.parse_time(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("value", ["2026-11-09T07:00:00", "not-a-date", ""])
def test_parse_time_rejects_missing_offset_or_garbage(value):
    with pytest.raises(MODULE.ExportError):
        MODULE.parse_time(value)


def test_validate_range_rejects_inverted_and_bad_steps():
    with pytest.raises(MODULE.ExportError, match="after"):
        MODULE.validate_range(BASE, BASE, 30)
    for step in (0, 9, 3601):
        with pytest.raises(MODULE.ExportError, match="step"):
            MODULE.validate_range(BASE, BASE.replace(hour=8), step)


def test_validate_range_enforces_the_step_cap():
    with pytest.raises(MODULE.ExportError, match="limit"):
        MODULE.validate_range(BASE, BASE.replace(year=2027), 10)


def test_validate_range_counts_steps():
    window = MODULE.validate_range(BASE, BASE.replace(minute=1), 30)
    assert window.steps == 3


# --- config ----------------------------------------------------------------


def test_default_config_is_valid_and_covers_the_core_signals():
    queries = MODULE.load_queries(DEFAULT_CONFIG)
    names = {query.name for query in queries}

    assert len(names) == len(queries)
    assert {
        "node_cpu_busy_ratio",
        "node_memory_available_bytes",
        "node_filesystem_avail_bytes",
        "pod_ready",
    } <= names
    assert all(query.unit in MODULE.ALLOWED_UNITS for query in queries)


def test_load_queries_reads_name_unit_and_description(tmp_path):
    queries = MODULE.load_queries(write_config(tmp_path, VALID_CONFIG))

    assert [query.name for query in queries] == [
        "node_memory_available_bytes",
        "node_cpu_busy_ratio",
    ]
    assert [query.unit for query in queries] == ["bytes", "ratio"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("queries: []", "no queries"),
        ("not-a-mapping", "queries"),
        ("queries:\n  - just-a-string\n", "mapping"),
        ("queries:\n  - name: 9bad\n    query: up\n    unit: bool\n", "invalid name"),
        ("queries:\n  - name: a b\n    query: up\n    unit: bool\n", "invalid name"),
        ("queries:\n  - name: ok\n    query: '  '\n    unit: bool\n", "empty expression"),
        ("queries:\n  - name: ok\n    query: up\n    unit: \n", "no unit"),
        ("queries:\n  - name: ok\n    query: up\n    unit: potatoes\n", "allowed units"),
        (
            "queries:\n  - name: ok\n    query: up\n    unit: bool\n    allow_empty: 1\n",
            "non-boolean",
        ),
        (
            "queries:\n"
            "  - name: dup\n    query: up\n    unit: bool\n"
            "  - name: dup\n    query: up\n    unit: bool\n",
            "duplicate",
        ),
    ],
)
def test_load_queries_rejects_invalid_config(tmp_path, text, message):
    with pytest.raises(MODULE.ExportError, match=message):
        MODULE.load_queries(write_config(tmp_path, text))


def test_load_queries_reports_a_missing_file(tmp_path):
    with pytest.raises(MODULE.ExportError, match="cannot read"):
        MODULE.load_queries(tmp_path / "absent.yaml")


# --- labels and series identity -------------------------------------------


def test_canonical_labels_drop_name_and_sort_keys():
    labels = MODULE.canonical_labels({"__name__": "up", "zone": "b", "instance": "x", "job": "a"})

    assert labels == '{"instance":"x","job":"a","zone":"b"}'
    assert json.loads(labels) == {"instance": "x", "job": "a", "zone": "b"}


def test_series_id_is_stable_and_metric_scoped():
    labels = MODULE.canonical_labels({"node": "n1"})

    assert MODULE.series_id("up", labels) == MODULE.series_id("up", labels)
    assert MODULE.series_id("up", labels) != MODULE.series_id("down", labels)
    assert len(MODULE.series_id("up", labels)) == 16


# --- row building ----------------------------------------------------------


def test_build_rows_keeps_only_observed_samples_no_fill():
    result = matrix({"node": "n1"}, [(T[0], "1"), (T[2], "2")])

    rows, skipped, series = MODULE.build_rows("up", "bool", "lab", result)

    assert series == 1
    assert skipped == 0
    assert [row["timestamp"].timestamp() for row in rows] == [T[0], T[2]]
    assert [row["value"] for row in rows] == [1.0, 2.0]
    assert all(row["site"] == "lab" for row in rows)
    assert rows[0]["labels"] == '{"node":"n1"}'


@pytest.mark.parametrize("raw", ["NaN", "Inf", "-Inf"])
def test_build_rows_skips_non_finite_values_without_filling(raw):
    result = matrix({"node": "n1"}, [(T[0], raw), (T[1], "3")])

    rows, skipped, series = MODULE.build_rows("node_cpu_busy_ratio", "ratio", "lab", result)

    assert skipped == 1
    assert series == 1
    assert [row["value"] for row in rows] == [3.0]
    assert len(rows) == 1


def test_build_rows_rejects_a_non_numeric_sample():
    result = matrix({"node": "n1"}, [(T[0], "not-a-number")])

    with pytest.raises(MODULE.ExportError, match="non-numeric"):
        MODULE.build_rows("up", "bool", "lab", result)


def test_summarise_reports_coverage_and_incomplete_series():
    rows = [
        {"series_id": "a", "timestamp": BASE, "value": 1},
        {"series_id": "a", "timestamp": BASE, "value": 1},
        {"series_id": "b", "timestamp": BASE, "value": 1},
    ]
    summary = MODULE.summarise(MODULE.QuerySpec(name="up", query="up", unit="bool"), rows, 2, 3)

    assert summary["samples"] == 3
    assert summary["expected_samples"] == 6
    assert summary["coverage"] == 0.5
    assert summary["series_below_full_coverage"] == 2


def test_summarise_never_divides_by_zero():
    summary = MODULE.summarise(MODULE.QuerySpec(name="up", query="up", unit="bool"), [], 0, 3)

    assert summary["coverage"] is None
    assert summary["empty"] is True
    assert summary["expected_samples"] == 0


def test_min_coverage_ignores_allowed_empty_queries():
    assert MODULE._min_coverage([{"coverage": None}, {"coverage": 0.5}, {"coverage": 0.9}]) == 0.5
    assert MODULE._min_coverage([{"coverage": None}]) is None


# --- HTTP ------------------------------------------------------------------


def test_safe_url_drops_userinfo_and_keeps_the_path():
    assert (
        MODULE.safe_url("http://user:secret@prom.example:9090/prefix")
        == "http://prom.example:9090/prefix"
    )
    assert MODULE.safe_url("http://127.0.0.1:9090") == "http://127.0.0.1:9090"


def test_fetch_matrix_accepts_a_matrix():
    query = MODULE.QuerySpec(name="up", query="up", unit="bool")
    window = MODULE.validate_range(BASE, BASE.replace(minute=1), 30)
    client = client_for({"up": matrix({"node": "n1"}, [(T[0], "1")])})

    result = MODULE.fetch_matrix(client, "http://127.0.0.1:9090", query, window)

    assert result[0]["values"] == [[T[0], "1"]]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"status": "error", "error": "parse error"}, "Prometheus error"),
        (
            {"status": "success", "data": {"resultType": "vector", "result": []}},
            "expected 'matrix'",
        ),
        (
            {"status": "success", "data": {"resultType": "matrix", "result": "nope"}},
            "malformed",
        ),
    ],
)
def test_fetch_matrix_rejects_bad_payloads(payload, message):
    query = MODULE.QuerySpec(name="up", query="up", unit="bool")
    window = MODULE.validate_range(BASE, BASE.replace(minute=1), 30)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(MODULE.ExportError, match=message):
        MODULE.fetch_matrix(client, "http://127.0.0.1:9090", query, window)


def test_fetch_matrix_turns_http_errors_and_timeouts_into_export_errors():
    query = MODULE.QuerySpec(name="up", query="up", unit="bool")
    window = MODULE.validate_range(BASE, BASE.replace(minute=1), 30)

    failing = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    with pytest.raises(MODULE.ExportError, match="request failed"):
        MODULE.fetch_matrix(failing, "http://127.0.0.1:9090", query, window)

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom", request=request)

    timing_out = httpx.Client(transport=httpx.MockTransport(timeout))
    with pytest.raises(MODULE.ExportError, match="timed out"):
        MODULE.fetch_matrix(timing_out, "http://127.0.0.1:9090", query, window)


def test_fetch_matrix_does_not_leak_url_userinfo_on_error():
    query = MODULE.QuerySpec(name="up", query="up", unit="bool")
    window = MODULE.validate_range(BASE, BASE.replace(minute=1), 30)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))

    with pytest.raises(MODULE.ExportError) as excinfo:
        MODULE.fetch_matrix(client, "http://user:secret@prom.example:9090", query, window)

    message = str(excinfo.value)
    assert "secret" not in message
    assert "http://prom.example:9090" in message


# --- end to end ------------------------------------------------------------


def test_export_writes_sorted_parquet_with_metadata_and_manifest(tmp_path):
    matrices = {
        "node_memory_MemAvailable_bytes": matrix({"node": "n1"}, [(T[0], "100"), (T[2], "300")]),
        '1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]))': matrix(
            {"node": "n1"}, [(T[0], "0.25"), (T[1], "0.5"), (T[2], "0.75")]
        ),
    }
    parquet_path, manifest_path, manifest = run_export(
        tmp_path,
        matrices,
        url="http://user:secret@prom.example:9090",
        window=MODULE.validate_range(BASE, BASE.replace(minute=1), 30),
    )

    assert parquet_path.exists()
    assert manifest_path.exists()
    table = pq.read_table(parquet_path)
    assert table.num_rows == 5
    assert table.column_names == [
        "timestamp",
        "metric",
        "unit",
        "series_id",
        "labels",
        "value",
        "site",
    ]
    metadata = table.schema.metadata
    assert metadata[b"export_schema"] == b"prometheus-export.v1"
    assert metadata[b"site"] == b"lab"
    assert json.loads(metadata[b"units"]) == ["bytes", "ratio"]
    assert metadata[b"no_zero_fill"] == b"true"

    rows = table.to_pylist()
    assert {row["metric"] for row in rows} == {
        "node_memory_available_bytes",
        "node_cpu_busy_ratio",
    }
    assert [
        row["timestamp"].timestamp()
        for row in rows
        if row["metric"] == "node_memory_available_bytes"
    ] == [
        T[0],
        T[2],
    ]
    sort_key = [(row["metric"], row["series_id"], row["timestamp"]) for row in rows]
    assert sort_key == sorted(sort_key)

    stored = json.loads(manifest_path.read_text())
    assert stored == manifest
    assert stored["prometheus"] == {"url": "http://prom.example:9090", "version": "3.5.0"}
    assert stored["range"] == {
        "start": "2026-11-09T07:00:00Z",
        "end": "2026-11-09T07:01:00Z",
        "step_seconds": 30,
        "steps": 3,
    }
    assert stored["site"] == "lab"
    assert stored["rows"] == 5
    assert stored["skipped_non_finite"] == 0
    assert stored["parquet"] == "metrics.parquet"
    assert (
        stored["config"]["sha256"]
        == hashlib.sha256((tmp_path / "queries.yaml").read_bytes()).hexdigest()
    )
    assert stored["queries"][0] == {
        "name": "node_memory_available_bytes",
        "unit": "bytes",
        "series": 1,
        "samples": 2,
        "expected_samples": 3,
        "coverage": 0.6667,
        "series_below_full_coverage": 1,
        "empty": False,
    }
    assert stored["queries"][1]["coverage"] == 1.0


def test_export_never_writes_a_filled_value_for_a_gap(tmp_path):
    window = MODULE.validate_range(BASE, BASE.replace(minute=1), 30)
    matrices = {
        "node_memory_MemAvailable_bytes": matrix({"node": "n1"}, [(T[0], "1"), (T[2], "2")])
    }
    config = write_config(
        tmp_path,
        "queries:\n  - name: node_memory_available_bytes\n"
        "    query: node_memory_MemAvailable_bytes\n    unit: bytes\n",
    )

    parquet_path, _, manifest = run_export(tmp_path, matrices, config=config, window=window)
    rows = pq.read_table(parquet_path).to_pylist()

    assert [row["timestamp"].timestamp() for row in rows] == [T[0], T[2]]
    assert len(rows) == 2
    assert manifest["queries"][0]["samples"] == 2
    assert manifest["queries"][0]["expected_samples"] == 3
    assert manifest["queries"][0]["coverage"] == 0.6667


def test_export_counts_non_finite_samples(tmp_path):
    matrices = {
        "node_memory_MemAvailable_bytes": matrix({"node": "n1"}, [(T[0], "NaN"), (T[1], "4")])
    }
    config = write_config(
        tmp_path,
        "queries:\n  - name: node_memory_available_bytes\n"
        "    query: node_memory_MemAvailable_bytes\n    unit: bytes\n",
    )

    parquet_path, _, manifest = run_export(
        tmp_path,
        matrices,
        config=config,
        window=MODULE.validate_range(BASE, BASE.replace(minute=1), 30),
    )

    assert pq.read_table(parquet_path).num_rows == 1
    assert manifest["skipped_non_finite"] == 1


def test_export_refuses_to_write_an_empty_dataset(tmp_path):
    def empty_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/status/buildinfo":
            return buildinfo()
        return range_response([])

    client = httpx.Client(transport=httpx.MockTransport(empty_handler))
    config = write_config(
        tmp_path,
        "queries:\n  - name: optional\n    query: missing_metric\n    unit: count\n"
        "    allow_empty: true\n",
    )
    output_dir = tmp_path / "empty"
    with pytest.raises(MODULE.ExportError, match="no samples"):
        run_export(tmp_path, {}, config=config, output_dir=output_dir, client=client)

    assert not (output_dir / "metrics.parquet").exists()
    assert not (output_dir / "manifest.json").exists()


def test_a_query_with_no_series_fails_unless_allowed(tmp_path):
    empty_only = write_config(
        tmp_path,
        "queries:\n  - name: optional\n    query: missing_metric\n    unit: count\n",
    )
    with pytest.raises(MODULE.ExportError, match="no series"):
        run_export(
            tmp_path,
            {},
            config=empty_only,
            output_dir=tmp_path / "fails",
            client=httpx.Client(transport=httpx.MockTransport(lambda request: range_response([]))),
        )
    assert not (tmp_path / "fails" / "metrics.parquet").exists()

    allowed = write_config(
        tmp_path,
        "queries:\n"
        "  - name: optional\n    query: missing_metric\n    unit: count\n"
        "    allow_empty: true\n"
        "  - name: node_memory_available_bytes\n"
        "    query: node_memory_MemAvailable_bytes\n    unit: bytes\n",
    )
    matrices = {
        "missing_metric": [],
        "node_memory_MemAvailable_bytes": matrix(
            {"node": "n1"}, [(T[0], "7"), (T[1], "7"), (T[2], "7")]
        ),
    }
    _, _, manifest = run_export(
        tmp_path,
        matrices,
        config=allowed,
        output_dir=tmp_path / "allowed",
    )

    empty_summary = manifest["queries"][0]
    assert empty_summary["empty"] is True
    assert empty_summary["series"] == 0
    assert empty_summary["coverage"] is None
    assert manifest["queries"][1]["coverage"] == 1.0


def test_export_does_not_close_a_caller_owned_client(tmp_path):
    matrices = {
        "node_memory_MemAvailable_bytes": matrix({"node": "n1"}, [(T[0], "1")]),
        '1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]))': matrix(
            {"node": "n1"}, [(T[0], "0.1")]
        ),
    }
    client = client_for(matrices)
    run_export(tmp_path, matrices, client=client)

    assert not client.is_closed
    client.close()


# --- CLI -------------------------------------------------------------------


def test_main_returns_2_on_an_invalid_range(tmp_path, capsys):
    exit_code = MODULE.main(
        [
            "--start",
            "2026-11-09T08:00:00Z",
            "--end",
            "2026-11-09T07:00:00Z",
            "--config",
            str(DEFAULT_CONFIG),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 2
    assert "after" in capsys.readouterr().err


def test_main_returns_2_when_the_config_is_invalid(tmp_path, capsys):
    exit_code = MODULE.main(
        [
            "--start",
            "2026-11-09T07:00:00Z",
            "--end",
            "2026-11-09T08:00:00Z",
            "--config",
            str(write_config(tmp_path, "queries: []")),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 2
    assert "no queries" in capsys.readouterr().err
