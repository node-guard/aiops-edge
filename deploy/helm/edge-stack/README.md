# edge-stack Helm chart (S2-B1)

Observability stack for **one edge site**: Prometheus, Alertmanager, node-exporter
and kube-state-metrics. It is self-contained on purpose — no
`kube-prometheus-stack`, no Prometheus Operator, no CRDs — so it renders
offline and fits a 2 vCPU / 2–3 GB node.

The AIOps services (detector, processor, connector, policy, executor, console)
are added to this chart in later tasks. Service identities are already created
so those components do not need to invent their own.

## What it installs

| Workload | Kind | Purpose |
|---|---|---|
| `edge-stack-prometheus` | StatefulSet + PVC | Scrapes the two exporters, keeps `168h` (7 days) of TSDB |
| `edge-stack-alertmanager` | StatefulSet | Receives alerts; v0 routes to a null receiver |
| `edge-stack-node-exporter` | DaemonSet | Node CPU, memory, disk, network on every node |
| `edge-stack-kube-state-metrics` | Deployment | Pod/workload object metrics (phase, restarts, requests) |

All resource names are prefixed with the release name (`edge-stack-...` when
installed as `edge-stack`).

## Prerequisites

- Kubernetes ≥ 1.28 (the lab runs K3s `v1.31.4+k3s1`).
- Helm 3.8+ or Helm 4 (`helm lint`, `helm template` are part of `make check`).
- A default StorageClass for the Prometheus PVC (`local-path` on K3s), or set
  `prometheus.persistence.storageClass`.
- Outbound access from the nodes to `quay.io` and `registry.k8s.io`, or the four
  images preloaded into the node image store. Images are pinned by tag and digest.

## Install

```bash
export KUBECONFIG="$PWD/deploy/lab/.state/kubeconfig"   # lab only
helm upgrade --install edge-stack deploy/helm/edge-stack \
  --namespace aiops-system --create-namespace

kubectl -n aiops-system get pods
kubectl -n aiops-system get pvc
```

The lab namespace for **fault injection** remains `aiops-test`; monitoring lives
in `aiops-system`. The lab guard only checks the cluster context, not the
namespace, so check the namespace yourself before applying anything.

## Verify

```bash
helm lint --strict deploy/helm/edge-stack
helm template edge-stack deploy/helm/edge-stack --namespace aiops-system >/dev/null
make check     # includes the chart render and tests/security/test_edge_stack_chart.py

kubectl -n aiops-system port-forward svc/edge-stack-prometheus 9090:9090
```

Then in the Prometheus UI or API:

```bash
curl -s localhost:9090/api/v1/targets | jq -r '.data.activeTargets[] | [.labels.job,.health] | @tsv'
curl -s 'localhost:9090/api/v1/query?query=up' | jq -r '.data.result[] | [.metric.job,.value[1]] | @tsv'
curl -s 'localhost:9090/api/v1/query?query=node_cpu_seconds_total' | jq '.data.result | length'
curl -s 'localhost:9090/api/v1/query?query=kube_pod_info' | jq -r '.data.result[] | [.metric.namespace,.metric.pod] | @tsv'
curl -s localhost:9090/api/v1/status/flags | jq -r '.data["storage.tsdb.retention.time"]'   # 1w
```

Expected: four targets `up` (Prometheus, two node-exporters, kube-state-metrics),
`16` CPU series per node (2 vCPU × 8 modes), and `kube_pod_info` reporting the
real namespace of each pod.

## Values

| Key | Default | Notes |
|---|---|---|
| `site.name` | `lab` | Prometheus external label; must match the site identity used centrally |
| `site.environment` | `lab` | `lab`, `staging` or `production` |
| `prometheus.retention` | `168h` | 7 days, required by SPEC §13 |
| `prometheus.scrapeInterval` | `30s` | |
| `prometheus.persistence` | `enabled: true`, `5Gi` | Set `storageClass` on multi-class clusters |
| `prometheus.resources` | `100m/256Mi` → `500m/512Mi` | Requests/limits are mandatory in the schema |
| `alertmanager.enabled` | `true` | Disabling removes the workload and the Prometheus `alerting` block |
| `alertmanager.retention` | `120h` | Alertmanager data retention |
| `nodeExporter.tolerations` | all taints | Must run on the control-plane node too |
| `kubeStateMetrics.collectedResources` | 12 object kinds | Never secrets or configmaps |
| `imagePullPolicy` | `IfNotPresent` | |

Unknown keys, malformed durations, unpinned tags/digests and invalid resource
quantities are rejected by `values.schema.json` before anything is applied.

## Security model

| Identity | Used by | Permissions |
|---|---|---|
| `aiops-telemetry` | Prometheus | `get/list/watch` on services, endpoints, pods (target discovery) |
| `aiops-observer` | kube-state-metrics | `get/list/watch` on the collected object kinds only |
| `aiops-remediation-executor` | not bound yet | **No token, no RBAC binding**; bound when the executor lands |

No wildcard verbs/resources, no `secrets`, no `configmaps`, no `exec`, no
`patch`, no `cluster-admin`. The executor ServiceAccount exists only so the
future executor can be bound deliberately.

node-exporter is the only workload with `hostNetwork`/`hostPID`; it mounts
`/proc`, `/sys` and `/` read-only and runs as UID 65534 with all capabilities
dropped. Everything else runs non-root with a read-only root filesystem and a
`RuntimeDefault` seccomp profile.

## Known gaps (v0)

- **No container-level CPU/memory (cAdvisor).** Scraping kubelet requires
  `nodes/proxy` (or `nodes/metrics` plus an apiserver proxy), which is outside
  the scrape-only role in SPEC §12. Node metrics and pod object metrics are
  available; per-container usage needs an explicit RBAC decision.
- **No alert rules or receivers.** Alertmanager is wired and running, but v0
  routes to a null receiver. Rules and notifications belong to the policy and
  notification tasks.
- **Single replica everywhere.** No HA; an edge site is one failure domain.
- **No NetworkPolicy.** Scraping is namespace-internal today; add policies when
  the connector and central link exist.

## Upgrade and removal

```bash
helm upgrade edge-stack deploy/helm/edge-stack -n aiops-system
helm uninstall edge-stack -n aiops-system
```

The Prometheus PVC (`data-edge-stack-prometheus-0`) is **not** removed by
`helm uninstall`; delete it deliberately if the history is disposable.
Alertmanager data is an `emptyDir` unless `alertmanager.persistence.enabled` is set.
