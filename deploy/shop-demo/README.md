# shop-demo (S1-B2)

A tiny, disposable HTTP service used as the target for faults F01, F02, F06,
F08, F14 and F15. It runs **only** in the disposable lab, namespace
`aiops-test`.

```
host ── NodePort :30080 ──► shop-demo (2 replicas)
                                  │
                                  └── shop-demo-db:5432 (PostgreSQL, 1 replica, PVC)
```

| Component | Image | Replicas | Resources |
|---|---|---|---|
| `shop-demo` | `shop-demo@sha256:…` (built from this repo) | 2 | 50m/64Mi → 500m/256Mi |
| `shop-demo-db` | `postgres:16.4-bookworm` | 1 | 100m/128Mi → 500m/512Mi |

The app exposes:

| Endpoint | Behaviour |
|---|---|
| `GET /` | Service name, version and endpoint list |
| `GET /health/live` | Always `200` while the process is alive; does **not** touch the DB |
| `GET /health/ready` | `200` when `SELECT 1` succeeds, `503` when the DB is down |
| `GET /work/cpu?seconds=10&workers=2` | Bounded CPU burn (1–60 s, 1–4 threads) |
| `GET /work/memory?mb=100&seconds=10` | Bounded memory hold (1–512 MiB, 1–60 s) |
| `GET /work/fail?mode=error` | Returns `500` (F08) |
| `GET /work/fail?mode=crash` | Exits the process after 0.2 s; Kubernetes restarts it (F08) |

Logs are one JSON object per line. The formatter redacts keys that look like
credentials (`password`, `token`, `secret`, `authorization`, `dsn`). The DSN is
never logged. Fault endpoints can be disabled with
`ENABLE_FAULT_ENDPOINTS=false` in `configmap.yaml`.

## Prerequisites

- The lab is up: `make lab-up`, then
  `export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"`.
- Docker on the host (the image is built locally).
- `kubectl`, `docker`, `ssh`, `scp`, `awk`.

`deploy/lab/lib/lab-guard.sh` runs before every deploy/delete and refuses any
context other than `aiops-lab`.

## Build and load the image

The lab has no registry. The build script builds the image, copies it to both
nodes with `ctr images import`, creates the digest tag containerd needs, and
pins the digest in `kustomization.yaml` and the Deployment annotation:

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"
make shop-demo-build
```

It prints the digest, for example:

```text
[lab] image digest: sha256:d221e511e98eb283a14906fe5e2fb36544031b9efb3a5d8ac7398e63c450a222
[lab] pinned sha256:d221e… in kustomization.yaml and app-deployment.yaml
```

Run it again after every code change **and** after `make lab-down --wipe`
(the containerd image store is inside the VMs). `--no-pin` only prints the
digest instead of editing the manifests.

## Deploy

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"
make shop-demo-deploy          # guard + kubectl apply -k deploy/shop-demo

kubectl -n aiops-test rollout status deploy/shop-demo-db --timeout=180s
kubectl -n aiops-test rollout status deploy/shop-demo --timeout=180s
kubectl -n aiops-test get pods -o wide
```

Expected: one `shop-demo-db` pod and two `shop-demo` pods, all `1/1 Running`.
The app is reachable from the lab host at
`http://192.168.100.10:30080` (or `http://192.168.100.11:30080`). There is no
ingress and no port forward on the host's external interface.

## Verify the healthy state

```bash
curl -sS http://192.168.100.10:30080/
# {"service":"shop-demo","version":"0.1.0","endpoints":[...]}

curl -sS -w ' [%{http_code}]\n' http://192.168.100.10:30080/health/live
# {"status":"ok","service":"shop-demo"} [200]

curl -sS -w ' [%{http_code}]\n' http://192.168.100.10:30080/health/ready
# {"status":"ready","database":"up"} [200]
```

Logs:

```bash
kubectl -n aiops-test logs -l app.kubernetes.io/component=app --tail=5
# {"ts":"…","level":"info","service":"shop-demo","msg":"…"}
```

## Break the database on purpose (F14)

```bash
kubectl -n aiops-test scale deploy/shop-demo-db --replicas=0

# Readiness must fail, liveness must stay up. Use port-forward or exec to hit
# one pod directly; the Service has no ready endpoints while both replicas are
# not ready.
POD=$(kubectl -n aiops-test get pods -l app.kubernetes.io/component=app -o jsonpath='{.items[0].metadata.name}')
kubectl -n aiops-test exec "$POD" -- python -c "
import urllib.request, urllib.error
for path in ('/health/live', '/health/ready'):
    try:
        r = urllib.request.urlopen('http://127.0.0.1:8080' + path, timeout=5)
        print(path, r.status, r.read().decode())
    except urllib.error.HTTPError as e:
        print(path, e.code, e.read().decode())
"
# /health/live 200 {"status":"ok","service":"shop-demo"}
# /health/ready 503 {"status":"not_ready","database":"OperationalError"}

kubectl -n aiops-test scale deploy/shop-demo-db --replicas=1
kubectl -n aiops-test rollout status deploy/shop-demo-db --timeout=180s
curl -sS -w ' [%{http_code}]\n' http://192.168.100.10:30080/health/ready
# {"status":"ready","database":"up"} [200]
```

The app pods do **not** restart during this cycle: readiness gates traffic,
liveness stays `200`.

## Fault hooks

No manifest edits are needed; the app reads these at request time.

| Fault | Command | What to observe |
|---|---|---|
| F01 CPU saturation | `curl 'http://192.168.100.10:30080/work/cpu?seconds=30&workers=2'` | `kubectl top pod` rises toward the 500m limit; latency grows |
| F02 memory pressure | `curl 'http://192.168.100.10:30080/work/memory?mb=120&seconds=30'` | pod memory rises by ~120 MiB |
| F06 pod killed | `kubectl -n aiops-test delete pod -l app.kubernetes.io/component=app --wait=false` | Deployment recreates the pod; readiness returns |
| F08 app failure | `curl 'http://192.168.100.10:30080/work/fail?mode=error'` (500) or `?mode=crash` (process exits) | failed requests / restart, then recovery |
| F14 dependency outage | scale the DB to 0 (above) | readiness `503`, liveness `200` |
| F15 low memory limit | `/work/memory?mb=300` with the 256Mi limit | `OOMKilled`, restart loop |

For F15, a 300 MiB allocation exceeds the container limit, so the kernel kills
the process; this is the intended demo of a limit that is too low, not a bug.

## Reset

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"
make shop-demo-delete      # guard + kubectl delete -k deploy/shop-demo
make shop-demo-deploy      # fresh DB, fresh PVC
```

`kubectl delete -k` removes the Deployment, Services, ConfigMap, Secret and
PVC (the database data is disposable). The `aiops-test` namespace itself is
owned by `make lab-up` and is left in place.

## Future digest pinning notes

- `kustomization.yaml` pins the app by digest (`shop-demo@sha256:…`).
- The PostgreSQL image is pinned by tag (`postgres:16.4-bookworm`); record its
  digest before promoting the demo beyond the lab.
- The example secret is public (`shop-demo-lab-only`) and exists only so the
  lab converges without extra setup. Replace `secret.yaml` before any use
  outside `aiops-test`.

## Not implemented / known gaps

- No Prometheus scrape endpoint; S2-B1 adds the edge stack and cAdvisor metrics.
  The workload endpoints are visible through `kubectl top` (metrics-server).
- No ingress, TLS or auth: the demo is a fault target, not a product.
- The app does not run schema migrations; it only executes `SELECT 1` for
  readiness. The database is empty by design.
