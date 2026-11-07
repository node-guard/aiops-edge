# Healthy workload generator (S2-B3)

Locust profiles that give the healthy-data soak realistic variation. They send
only **read-only** requests to `shop-demo`; the `/work/cpu`, `/work/memory` and
`/work/fail` hooks belong to the fault harness and are never called here.

## Why this exists

A flat idle cluster produces flat metrics. The anomaly detector and the future
predictive module need a baseline that includes ordinary variation: page views,
health probes, and short traffic bursts. This generator supplies that variation
without creating incidents, restarting pods, or touching Prometheus.

## Profiles

| Profile | Stages | Duration | Peak users | Purpose |
|---|---|---|---|---|
| `smoke` | 3 users, 1/s ramp | 1 min | 3 | Verify the runner and connectivity |
| `standard` | warm-up 5 → steady 10 → burst 25 → recovery 8 | 21 min | 25 | Daily healthy cycle during the soak |

With the 1–3 s think time, 25 users produce roughly **8–13 requests/second**,
about 2 of which hit `/health/ready` and therefore PostgreSQL. That stays well
inside the 2 vCPU / 2 GiB worker budget.

`standard` is a cycle, not a daemon: run it again (or schedule it) to keep the
variation going. Do not restart Prometheus to schedule it; the load runner is
an external HTTP client on the host and is not part of the measured system.

## Run

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"

make load PROFILE=smoke                  # 1-minute connectivity check
make load PROFILE=standard               # 21-minute healthy cycle

# or directly
HOST=http://192.168.100.10:30080 LOAD_PROFILE=standard bash experiments/load/run.sh
```

Output is written to `experiments/runs/load-<UTC stamp>/`:

- `meta.txt` — profile, host, start time, commit;
- `load_stats.csv`, `load_failures.csv`, `load_stats_history.csv` — Locust output.

The folder is git-ignored; keep only the summary numbers in
`experiments/NOTES.md` or an analysis notebook.

## Expected effect

| Signal | During `standard` |
|---|---|
| `node_cpu_seconds_total` (worker) | small rise during the burst stage, back to baseline in recovery |
| Pod CPU (when cAdvisor exists) | proportional to request rate |
| `kube_pod_restart_total` | **must stay 0** |
| `/health/ready` latency | rises with DB connection churn; still well under 1 s |

If p95 latency stays above 1 s, or node CPU stays above 80% for more than five
minutes, stop the run: that is no longer a *healthy* baseline, it is a load
problem, and its data must not be mixed into the soak.

## Limits and honest gaps

- `shop-demo` has no catalogue or cart endpoints; the "realistic" behaviour is
  limited to the home page and the two health probes. When the demo grows a
  product/search endpoint, add it to `locustfile.py` with a task weight.
- The generator runs on the host, not inside the cluster. That keeps the
  measured nodes clean but means the host must stay awake for a full cycle.
- It creates no fault and writes no run metadata beyond `meta.txt`; the fault
  harness (S2-B2) owns `meta.json` and the run index.
