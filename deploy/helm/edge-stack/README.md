# edge-stack Helm chart (S2-B1)

Umbrella chart for one site: Prometheus, Alertmanager, node-exporter, kube-state-metrics, then the AIOps services (detector, processor, connector, policy, executor, console).
Requirements: `values.schema.json`; resource requests/limits on every pod; ServiceAccounts `aiops-observer`, `aiops-remediation-executor`, `aiops-telemetry` with the RBAC in SPEC §12; `automountServiceAccountToken: false` where not needed; no secrets in values files.
