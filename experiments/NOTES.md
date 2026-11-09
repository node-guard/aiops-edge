# Lab notebook

Dated entries: what changed, why, observations, anomalies. Keep newest first. Record maintenance windows that affect the healthy-data soak.

## 2026-11-09 — Lab back up, soak restarted, F02 verified

`make lab-up` at 2026-11-09T07:14Z redefined and booted both VMs (they were
undefined after the host shutdown; disks and state were intact). K3s reported
2/2 Ready nodes and every workload restarted cleanly.

### Soak restart

**New Prometheus container start: 2026-11-09T07:16:42Z.** `restarts=1` on the
container (the restart caused by the VM boot, not a crash). The TSDB is the same
PVC, but the container uptime counters and the soak clock restarted.

| Item | Value |
|---|---|
| Soak start | **2026-11-09T07:16:42Z** |
| Earliest completion | **2026-11-14T07:16:42Z** (5 continuous days) |
| Targets | 4/4 `up` (Prometheus, node-exporter ×2, kube-state-metrics) |
| Pods | 5/5 monitoring ready, **0 crash restarts after boot** |
| PVC | `Bound`, 5 GiB, same `pvc-e700e3e4-…` |
| Retention | `1w` (168h) |
| Old data | 2026-11-07 series remain queryable until they age out |

### F02 memory pressure verified

`run_id=20261109T071821Z-F02-18bd51`, 60 s, 128 MiB, HTTP 200, **valid**,
duration 60.386 s. The request was served by `shop-demo-d74cbcf99-zc9ls` on
`aiops-edge-worker` (confirmed by the `workload_finished` log line).

| Signal (worker, 30 s scrapes) | Before (07:17:30Z) | During (07:18:00–30Z) | After (07:19:00Z) |
|---|---|---|---|
| `node_memory_MemAvailable_bytes` | 1,506 MiB | 1,380 → 1,360 MiB | 1,484 MiB |

The 128 MiB allocation is visible as a ~146 MiB drop in available memory and is
released when the request returns (a ~22 MiB residual is ordinary allocator/page
churn, not the fault). No pod restarted, no OOM kill, no readiness failure.

### Standard load cycle

`make load PROFILE=standard` started **2026-11-09T07:19:03Z** (21-minute cycle)
so the restarted soak is not a flat idle baseline. Result to be appended below
when the cycle finishes.

## 2026-11-08 — Lab VM off: soak interrupted

The lab VM (`ubuntu26.04`) was found `shut off` at **2026-11-08T19:58Z**; the
API server `192.168.100.10:6443` times out and `kubectl` cannot reach the
cluster.

| Item | Value |
|---|---|
| Last confirmed lab activity | 2026-11-07T07:18:22Z (end of the `standard` load cycle) |
| Found down | 2026-11-08T19:58Z |
| Measured gap | ≈ 48 h: last data 2026-11-07T07:18:22Z, new Prometheus start 2026-11-09T07:16:42Z (host shutdown time unknown) |
| Affected | Prometheus scrape continuity, the 5-day soak clock, F02 lab verification |

The TSDB and PVC survive a VM stop, but the Prometheus container start time
resets when the lab is booted again. **The 5-continuous-day clock therefore
restarts from the next Prometheus start**, and the retention proof date moves
accordingly. The 2026-11-07 data stays queryable until it ages out (7-day
retention). The `standard` load cycle ended cleanly before the outage, so its
numbers below remain valid.

No daily check was possible on 2026-11-08 beyond "cluster unreachable"; that is
the recorded observation.

### Standard load cycle result (2026-11-07T06:57:22Z → 07:18:22Z)

| Endpoint | Requests | Failures | Median | p95 | Max |
|---|---|---|---|---|---|
| `GET /` | 3,974 | 0 | 3 ms | 4 ms | 207 ms |
| `GET /health/live` | 1,857 | 0 | 3 ms | 5 ms | 249 ms |
| `GET /health/ready` | 1,279 | 0 | 11 ms | 18 ms | 400 ms |
| **Aggregated** | **7,110** | **0** | **3 ms** | **12 ms** | **400 ms** |

Average 5.64 req/s over the full 21-minute cycle (burst stage peaked at 25
users). No failure, and pods still reported `restarts=0` when the F01 run was
checked at 07:08Z. Raw CSV is in a git-ignored `experiments/runs/load-*` folder.

### Fault harness F01 (2026-11-07T07:07:58Z)

`run_id=20261107T070758Z-F01-96b8c7`, `seconds=30`, `workers=2`, HTTP 200,
valid, duration 30.068 s. Worker node CPU (1-minute average) rose from 2.9–3.1%
to 15.3% during the run and returned to ~3% afterwards; the server node stayed
flat. This is a real but modest signal: two busy loops on a 2-vCPU node that
already runs other pods.

**F02 was not run: the lab went down before it could be verified.**

## 2026-11-07 — Healthy-data soak started (S2-B4)

**Start (UTC): 2026-11-07T06:31:53Z.** This is the Prometheus container start
after the last chart fix (relabel correction); the TSDB was reset immediately
before it, so the series after this timestamp are clean and continuous.

| Item | Value |
|---|---|
| Chart | `edge-stack-0.1.0`, Helm revision 3, commit `cd5dbef` |
| Cluster | K3s `v1.31.4+k3s1`, 2 nodes, Debian 12 |
| Nodes | server 2 vCPU / 3 GiB (`192.168.100.10`), worker 2 vCPU / 2 GiB (`192.168.100.11`) |
| Prometheus | scrape `30s`, retention `168h`, 5 GiB local-path PVC (`pvc-222bdaa3-…` created 06:31:48Z) |
| Labels | `site=lab`, `environment=lab` |
| Workload | `shop-demo` (app + PostgreSQL) in `aiops-test`, no synthetic load yet |
| Earliest completion | **2026-11-12T06:31:53Z** (5 continuous days) — invalidated by the 2026-11-08 outage above |

**Rule:** do not restart, upgrade or reconfigure Prometheus for convenience.
Adding workloads or namespaces is fine; changing the Prometheus deployment,
scrape config or PVC is a soak interruption and must be logged here with the
reason and duration. The Prometheus pod carries a config checksum annotation,
so any edit to the chart values that affects it will roll the pod.

### Baseline checkpoint (2026-11-07T06:50Z, ~18 min after start)

| Check | Result |
|---|---|
| Targets | 4/4 `up` (Prometheus, node-exporter ×2, kube-state-metrics) |
| Pods | 5/5 ready, **0 restarts** |
| PVC | `Bound`, 5 GiB |
| Retention flag | `1w` (168h) |
| Head series | 3,119 |
| Node CPU series | 16 per node (2 vCPU × 8 modes) |
| Namespaces in `kube_pod_info` | `aiops-system`, `aiops-test`, `default`, `kube-node-lease`, `kube-public`, `kube-system` |
| Known gap | no per-container CPU/memory (cAdvisor); node + pod object metrics only |

### Load generator (S2-B3), 2026-11-07

- `make load PROFILE=smoke` at 06:56Z: 90 requests, **0 failures**, median 3 ms,
  max 19 ms, 1.51 req/s; no pod restart.
- `make load PROFILE=standard` started 06:57:22Z (21-minute cycle: 5 → 10 → 25
  → 8 users); output in a git-ignored `experiments/runs/load-*` folder.
- The generator runs on the host and only performs GETs on `/`,
  `/health/live` and `/health/ready`; it never calls `/work/*`.

### Daily check (once per day)

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"
kubectl -n aiops-system get pods,pvc
kubectl -n aiops-system port-forward svc/edge-stack-prometheus 9090:9090 &

# All targets still up
curl -s 'localhost:9090/api/v1/query?query=up' | jq -r '.data.result[] | [.metric.job,.value[1]] | @tsv'

# No scrape gaps in the last hour (expected ≈120 samples at 30s; alert if < 110)
curl -s 'localhost:9090/api/v1/query?query=count_over_time(up%5B1h%5D)' | jq -r '.data.result[] | [.metric.job,.metric.instance,.value[1]] | @tsv'

# Retention and TSDB size
curl -s localhost:9090/api/v1/status/flags | jq -r '.data["storage.tsdb.retention.time"]'
curl -s localhost:9090/api/v1/status/tsdb | jq '.data.headStats'
```

Record the numbers (or the anomaly) in this file, then stop the port-forward.

### Retention proof (at the end of the soak)

After ≥ 5 days, show that data older than 4 days still exists and that the
configured retention is 7 days:

```bash
curl -s 'localhost:9090/api/v1/query?query=timestamp(node_cpu_seconds_total)%20-%20time()' | jq '.data.result[0].value[1]'
curl -s localhost:9090/api/v1/status/flags | jq -r '.data["storage.tsdb.retention.time"]'
```

### Interruptions

| Time (UTC) | What | Reason | Duration |
|---|---|---|---|
| 2026-11-08T19:58Z (found) | Lab VM off, Prometheus not running | Host shut down after the 2026-11-07 session; soak clock restarts at next start | ≈ 48 h (2026-11-07T07:18Z → 2026-11-09T07:17Z) |

## 2026-11-02

- Repo created from the starter pack. Nothing measured yet.

