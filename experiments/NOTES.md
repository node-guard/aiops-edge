# Lab notebook

Dated entries: what changed, why, observations, anomalies. Keep newest first. Record maintenance windows that affect the healthy-data soak.

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
| Earliest completion | **2026-11-12T06:31:53Z** (5 continuous days) |

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
| — | none | — | — |

## 2026-11-02

- Repo created from the starter pack. Nothing measured yet.

