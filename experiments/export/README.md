# Prometheus -> Parquet export (S2-B5)

Turns the raw Prometheus series of the lab (or a real site with the same
`edge-stack` chart) into a Parquet dataset that the feature pipeline (S4-B1)
can read without talking to Prometheus. This is the boundary between
telemetry collection and ML: no feature engineering happens here.

## Why long format

The output has one row per observed sample:

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | `timestamp[us, UTC]` | sample time as returned by Prometheus |
| `metric` | string | `name` from `queries.yaml` (not `__name__`; queries can be expressions) |
| `unit` | string | unit declared in `queries.yaml` |
| `series_id` | string | first 16 hex chars of SHA-256 over `metric\nlabels` |
| `labels` | string | canonical JSON of the label set (keys sorted, `__name__` dropped) |
| `value` | float64 | observed sample |
| `site` | string | site identity passed with `--site` |

One file can hold several metrics and several series per metric; `series_id`
is stable across exports as long as the labels do not change, so features stay
joinable. The Parquet schema metadata also records `export_schema`, `site`,
the list of `units` and `no_zero_fill=true`.

## No zero-fill, and coverage

A gap in Prometheus (scrape failure, pod restart, network cut) is a gap in the
Parquet file: the exporter never writes `0`, never interpolates and never
forward-fills. Consumers must treat missing rows as missing data.

`manifest.json` reports, per query:

```json
{
  "name": "node_memory_available_bytes",
  "unit": "bytes",
  "series": 2,
  "samples": 240,
  "expected_samples": 240,
  "coverage": 1.0,
  "series_below_full_coverage": 0
}
```

`expected_samples = series × steps`, where `steps` is derived from
`--start`, `--end` and `--step`. Coverage below `1.0` means at least one
series had missing timestamps. Two expected causes:

- the window starts before the series existed (new pod, Prometheus restart);
- `rate()`-based queries need a trailing window before their first value, so
  the first few steps of a CPU/network query are legitimately absent.

A query that returns **no series at all** fails the export unless it is marked
`allow_empty: true` in the config. A wrong metric name must not silently turn
into a missing feature; this is how the exporter caught
`node_disk_write_bytes_total` vs the real `node_disk_written_bytes_total`.
For an allowed-empty query the manifest reports `"series": 0`, `"coverage":
null` and `"empty": true` instead of pretending coverage is zero.

A series that is completely absent from Prometheus cannot be counted, so
`series_below_full_coverage` only covers series that appeared at least once.
The feature pipeline decides whether to drop, mask or reject a window; this
exporter only reports.

## Prerequisites

Prometheus is a `ClusterIP` service. Forward it from the host:

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"
kubectl -n aiops-system port-forward svc/edge-stack-prometheus 9090:9090
```

Keep the forward running for the duration of the export. The exporter talks
only to that local URL; it needs no cluster credentials, no kubeconfig and no
write access to the cluster.

## Run

```bash
# 2026-11-09 07:00-08:00 UTC, 30 s step (the scrape interval)
make export START=2026-11-09T07:00:00Z END=2026-11-09T08:00:00Z

# longer window: raise the step to stay under the 10,000-step cap
make export START=2026-11-09T07:00:00Z END=2026-11-10T07:00:00Z STEP=60
```

Options (all available through `make export` or directly):

| Option | Default | Notes |
|---|---|---|
| `START`, `END` | required | RFC 3339 with an offset; end is inclusive |
| `STEP` | `30` | seconds, 10..3600 |
| `SITE` | `lab` | written to every row and to the manifest |
| `CONFIG` | `experiments/export/queries.yaml` | query/unit definitions |
| `URL` | `http://127.0.0.1:9090` | Prometheus base URL |
| `OUTPUT_DIR` | `experiments/runs/export-<UTC>-<id>/` | must be writable |

Output folder (git-ignored):

```
experiments/runs/export-20261109T080000Z-a1b2c3/
├── metrics.parquet
└── manifest.json
```

The command prints a one-line JSON summary (`parquet`, `manifest`, `rows`,
`queries`, `min_coverage`, `skipped_non_finite`).

## Failure behaviour

The exporter exits `2` and writes **no Parquet file** when:

- a timestamp has no offset, `end <= start`, or the step is outside 10..3600 s;
- the requested window needs more than 10,000 steps;
- the query config is invalid (bad name, duplicate name, empty expression,
  missing or unknown unit);
- Prometheus is unreachable, times out, returns a non-matrix result, or an
  error status;
- a query returns no series and is not marked `allow_empty: true`;
- every query returns zero samples (an empty export is never written);
- a sample value is not numeric (a truncated float must not become a feature).

`NaN` and `±Inf` samples (Prometheus's representation of undefined `rate()`)
are skipped and counted in `skipped_non_finite`; they do not fail the export.

The manifest stores the config path and SHA-256, the Prometheus version, the
range and step, the exporter version and the git commit, so an export can be
reproduced. Userinfo in `--url` is removed before it is written or logged.

## Limits

- Prometheus retention is 7 days (`168h`); older windows return nothing.
- The 10,000-step cap keeps a single query response small enough for a 2 GiB
  edge node. At the 30 s scrape interval that is ~83 hours of data; use
  `STEP=60` (7,200 steps for 5 days) for the full soak.
- This script reads the query API only. It does not scrape, write to
  Prometheus, or touch Kubernetes objects.
- Feature windows, ratio features and `node_role` are S4-B1; this exporter
  deliberately contains no feature logic.

## Tests

`tests/unit/test_prometheus_export.py` uses `httpx.MockTransport`, so it needs
no Prometheus and no cluster: config validation, label/series stability,
non-finite skipping, gap handling (no filled rows), coverage math, range/step
guards, URL redaction, Parquet round-trip and failure paths.
