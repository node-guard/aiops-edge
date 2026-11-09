# Fault harness v0 (S2-B2)

`run_fault.py` injects a fault into the disposable lab, writes one schema-valid
`meta.json` per run, and appends a row to the run index. It is the ground-truth
source for the whole experiment pipeline: detection metrics are computed against
the labelled window this script records.

## Safety guard (fail closed)

Every run checks, in this order, and refuses with exit code 2 if any check fails:

1. `kubectl` current context is exactly `aiops-lab`;
2. that context's API server is exactly `AIOPS_LAB_SERVER`
   (default `https://192.168.100.10:6443`);
3. the target namespace is exactly `aiops-test`;
4. `shop-demo` has at least one available replica and answers `/health/ready`;
5. F02 only: the container memory limit is readable and the request fits below it.

A missing kubeconfig, an unreachable API server or a kubectl timeout is an error,
never a default. Nothing is written when a guard fails.

## Faults

| ID | Endpoint | Parameters | Bounds |
|---|---|---|---|
| F01 CPU saturation | `GET /work/cpu` | `seconds`, `workers` | 1–60 s, 1–4 workers |
| F02 memory pressure | `GET /work/memory` | `seconds`, `mb` | 1–60 s, 1–512 MiB, and `mb ≤ limit − 64` |

The injector is the `shop-demo` workload endpoint, not `stress-ng`. The effect is
the same (busy-loop CPU on `workers` threads; `mb` touched pages held for
`seconds`) and it needs no extra image, privilege or DaemonSet. This deviates
from the wording in `docs/FAULT_MATRIX.md`, which names `stress-ng`; the matrix
records the v0 endpoint. Revisit when F03 (disk) needs a real I/O generator.

### F02 headroom

The app container limit is `256Mi`, so the default `--mb 128` uses half of it and
the ceiling is `192Mi`. The limit is read from the live deployment at run time,
not hard-coded: changing the manifest changes the guard. A limit that cannot be
read (missing, unparsable, API down) refuses the run instead of guessing.

## Usage

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"

uv run python experiments/harness/run_fault.py F01 --seconds 30 --workers 2
uv run python experiments/harness/run_fault.py F02 --seconds 30 --mb 128
```

Exit codes: `0` valid run, `1` run recorded with `valid=false` (injection failed),
`2` refused before injecting (guard, bounds, cluster unreachable).

## Outputs

Per run, `experiments/runs/<run_id>/`:

- `meta.json` — validated against `contracts/schemas/run-meta.v1.schema.json`.
  `run_id` is `<UTC stamp>-<fault>-<6 hex>`, e.g.
  `20261107T070758Z-F01-96b8c7`;
- `window.json` — parameters, start/end, duration, HTTP status, error.

`config_hash` is a SHA-256 over fault id, target, parameters, component versions
(K3s version, `shop-demo` image digest, harness commit) and harness version, so
two runs are comparable only if their hash matches.

`experiments/runs/index.parquet` is the append-only index (one row per run:
`run_id`, `fault_id`, `target`, `t_injection`, `t_end`, `duration_seconds`,
`valid`, `config_hash`, `meta_path`). It is single-writer: do not run two
harnesses at once. The file and the per-run folders are git-ignored; the index
can be rebuilt from the `meta.json` files if lost.

## Tests

`tests/unit/test_run_fault.py` covers the guard (wrong context, wrong server,
wrong namespace), bounds, the F02 ceiling and fail-closed paths, the frozen
schema (unknown fields, `valid=false` requires a reason), hash stability, run id
format, index append and kubectl timeout handling. No cluster is required.

## Status

| Run | Verified in the lab |
|---|---|
| F01 CPU, 30 s, 2 workers | yes — HTTP 200, 30.07 s, worker CPU 2.9% → 15.3% |
| F02 memory, 128 MiB, 60 s | yes — HTTP 200, 60.39 s, worker available memory 1,506 → 1,360 MiB, recovered to 1,484 MiB; no restart |

## Known gaps

- Node-level metrics only (no cAdvisor): F02 shows as a node memory drop, not a
  container memory rise, and the worker may be the non-targeted replica's node.
- One HTTP request hits one pod behind the Service; the harness does not pin the
  fault to a chosen replica.
- `t_impact` and `t_detection` stay `null` in v0. They are filled by the
  detection evaluation (S4+) from the labelled window, not by the harness.
