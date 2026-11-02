# Technical Specification (trimmed MVP)

Status: baseline v1.0, 2026-11-02. Product intent lives in `PRD.md`; this file is the build contract. Machine-readable contracts are in `/contracts` and **win over prose** on any conflict (then open an ADR).

Decision classes: **LOCKED** (change only via ADR) · **DEFAULT** (start here, validate) · **HYPOTHESIS** (test, do not assume) · **DEFERRED**.

## 1. Conventions

- All timestamps UTC, RFC 3339. Keep `occurred_at`, `observed_at`, `received_at`, `processed_at` separate.
- IDs: internal UUIDv4; Kubernetes UIDs stored alongside; never trust tenant/site from payload, derive from the authenticated identity.
- Delivery: at-least-once transport, idempotent processing. Unique keys: events `(site_id, event_id)`, incident updates `(site_id, local_incident_id, version)`, commands `command_id` plus local execution record.
- Missing metrics are never converted to zero; mark stale/missing.
- API errors: RFC 9457 Problem Details.
- Python 3.12, type-hinted, `ruff` + `mypy --strict` on `src/aiops/contracts` and `src/aiops/common`, standard mypy elsewhere.

## 2. Stack (LOCKED unless noted)

| Concern | Choice |
|---|---|
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic; separate worker process; PostgreSQL (+ pgvector, P1 RAG) |
| Edge state | SQLite (WAL) for incidents, outbox, action history, policy snapshot, sync cursors |
| Telemetry | Prometheus, Node Exporter, kube-state-metrics, kubelet/cAdvisor, Alertmanager (OTel Collector DEFERRED) |
| ML | scikit-learn, pandas/Polars, Parquet, joblib model packages |
| AI | LangGraph, Pydantic tool schemas; LLM behind a provider interface (cloud API default; local model DEFERRED) |
| Frontend | React + TypeScript + Vite, Tailwind + shadcn/ui, React Router, TanStack Query/Table, Recharts, Vitest + Playwright |
| Auth (DEFAULT) | Local users (argon2id), server-side session in HttpOnly/Secure/SameSite=Lax cookie, CSRF token, roles operator/approver/viewer; OIDC DEFERRED |
| Site identity | Mini-CA, single-use enrollment token, local key + CSR, mTLS |
| Deploy | Central: Docker Compose. Edge: Helm umbrella chart `edge-stack` on K3s. Lab: QEMU/libvirt |
| Tooling | `uv`, `pytest`, `ruff`, `mypy`, GitHub Actions, Make |

## 3. Components and topology

Independent K3s cluster per site (one server + agents; gateway services colocated on the server; not HA). Central never opens inbound connections to a site.

Central: reverse proxy, FastAPI API, worker, PostgreSQL, artifact volume (model packages).
Edge: Prometheus, Alertmanager, Node Exporter, kube-state-metrics, `detector`, `processor`, `connector`, `policy`, `executor`, `console_api` (see `src/aiops/edge/*`). Diagrams: `ARCHITECTURE.md`.

Offline behaviour: see `AUTONOMY_MATRIX.md` (authoritative). Rule: connectivity loss never upgrades L2 to L1; expired/invalid local policy disables automatic remediation but not observation or incident persistence.

## 4. Telemetry

| Setting | Value | Class |
|---|---|---|
| Scrape interval | 15 s | DEFAULT |
| ML windows | 1 min, 5 min | DEFAULT |
| Inference interval | 30 s | DEFAULT |
| Metrics retention | 7 days | DEFAULT |
| Logs | container logs with rotation, 3-7 days; bounded retrieval via observer RBAC (`pods/log`) | DEFAULT |
| Central metric storage | none; central keeps summaries and incident evidence only | LOCKED |

Identity hierarchy: tenant → site → cluster → node → namespace/workload/pod/container. Avoid high-cardinality labels.

## 5. Machine learning

### 5.1 Detector
One shared node-level detector per site. Emits `node.anomaly.detected` with `model_id`, `model_version`, `feature_schema_version`, `window_seconds`, `anomaly_score`, `threshold` and **`top_features`** (per-feature robust z-score or MAD deviation, top 3) so the LLM and operators get an explanation. Container/workload signals stay diagnostic context with deterministic rules.

### 5.2 Models and baselines
`ML-B0` static thresholds · `ML-B1` MAD/EWMA · `ML-B2` Isolation Forest (primary, **HYPOTHESIS** H1) · `ML-B3` LOF novelty mode (P1).

Features use **ratios and normalised values** plus a `node_role` feature (server/worker) so one shared model is comparable across heterogeneous nodes; if H1 fails per role, fall back to per-role scalers (ADR needed).

### 5.3 Training protocol
Healthy data only for fit; split by time block or whole fault run, never random adjacent windows; thresholds chosen on validation, not test; contamination is not a failure rate. Model package: `model.joblib`, `preprocessing.joblib`, `feature-schema.json`, `threshold-config.json`, `manifest.json`, `SHA256SUMS`. No automatic retraining; manual promotion. Concept drift is a stated limitation.

### 5.4 Predictive module (new vs the original spec)
Forecast time-to-exhaustion for disk usage and available memory per node (Prometheus `predict_linear` as baseline; Holt-Winters/robust linear fit as the compared method). Emit `node.resource.exhaustion_predicted` with `resource`, `eta_seconds`, `confidence_hint`, `horizon_seconds`. Metrics: lead time before exhaustion, absolute ETA error, false predictions per node-day. Faults: F17 (slow memory leak) and F18 (gradual disk fill).

## 6. Events, correlation, incidents

Envelope: CloudEvents-compatible (`contracts/schemas/event-envelope.v1.schema.json`).

Event types (v1): `node.anomaly.detected`, `node.resource.exhaustion_predicted`, `node.health.changed`, `k8s.pod.state_changed`, `k8s.deployment.health_degraded`, `app.health_check.failed`, `network.probe.degraded`, `alert.firing`, `site.connectivity.changed`, `remediation.execution.completed`, `remediation.verification.failed`.

Local correlation: temporal proximity + resource hierarchy + entity identity + known fingerprints + dependency topology. No learned correlation model. Central correlation across sites is P1; a central incident has its own identity.

Incident states: `NEW → TRIAGING → INVESTIGATING → (AWAITING_APPROVAL → REMEDIATING → VERIFYING → RESOLVED) | ESCALATED | FALSE_POSITIVE | FAILED`; recurrence may reopen; every transition appended to history. Local incident carries a monotonically increasing site `version`; central keeps `(site_id, local_incident_id)` → central incident link. Duplicate version ack, stale version ignore, same-version conflicting content reject + audit.

## 7. Agentic investigation

One central LangGraph agent. The LLM is **not** a security principal: no kubeconfig, no shell, no arbitrary code, no write path to the executor.

Workflow: load incident/site context → check authorization and data freshness → deterministic initial context (topology, recent changes) → LLM selects tools with typed args → **arguments validated outside the model** → run tools on the site via the command channel → (P1) retrieve runbooks/validated history → structured RCA → optional action proposal.

Tools (all read-only, bounded output, per-tool caps): `get_node_metrics`, `get_node_status`, `get_container_metrics`, `get_pod_status`, `get_previous_container_logs`, `search_application_logs`, `get_service_health`, `get_network_metrics`, `get_dependency_graph`, `get_recent_deployments`, `search_runbooks` (P1), `get_related_incidents`. `search_application_logs` is implemented as filtered `pods/log` retrieval, not a log store.

Limits per investigation (DEFAULT): ≤ 12 tool calls, ≤ 120 s wall time, ≤ configured token budget, bounded retrieved bytes. On timeout return `inconclusive`; never fabricate.

Output: `contracts/schemas/rca-report.v1.schema.json`. Model-reported confidence is not a calibrated probability.

Prompt-injection rules: logs/events/runbooks are untrusted data inside delimited blocks; fixed tool schemas; redact secrets before any external model call; persist prompt/model/tool versions and evidence, not hidden reasoning. Prompts live in `/prompts`.

**Command-channel latency (DEFAULT):** the site opens an outbound long-poll `GET /edge/v1/commands?wait=25`; central responds immediately when a command is queued. Target p50 round-trip for a diagnostic call < 2 s on the lab LAN; measure and report. (Upgrade to a persistent outbound stream only by ADR.)

## 8. Remediation

Levels: L0 read-only, L1 pre-authorized bounded, L2 approval required, L3 prohibited. Per-action level and triggers are defined in `AUTONOMY_MATRIX.md` and `contracts/actions/actions.yaml`.

Actions: **ACT-001** restart allowlisted stateless Deployment (rollout annotation); **ACT-002** scale allowlisted Deployment within `min/max` via the scale subresource; **ACT-003** rollback to previous revision (P1, always L2). No arbitrary shell, unrestricted kubectl, cluster-admin, PV/namespace deletion, or generic mutation.

Central Remediation Manager validates: actor permission, catalogue, target UID, tenant/site relation, typed payload, policy version, level, expiry, approval. Approver ≠ requester; any change to parameters or target invalidates the approval. The local policy engine repeats the critical checks. Deterministic Python policy engine (OPA deferred).

Command lifecycle: `PROPOSED → VALIDATING → (REJECTED | AWAITING_APPROVAL → APPROVED) → DISPATCHED → ACCEPTED → EXECUTING → EXECUTED → VERIFYING → SUCCEEDED | FAILED/ESCALATED`; also `EXPIRED`, `CANCELLED`. Operation success is not incident resolution; proposal, command, operation and incident states are stored separately.

Verification (DEFAULT): check every 15 s, require ≥ 2 min healthy, extended window up to 5 min. No generic automatic retry or rollback.

Clock skew: command/policy expiry compare against the site clock with a configurable tolerance (DEFAULT 30 s); the site must have NTP/chrony; if drift beyond tolerance is detected, automatic remediation is disabled (fail closed).

## 9. Resource budget and acceptance targets (proposed; freeze by end of S4 / S11)

| Item | Proposed target | Class |
|---|---|---|
| AIOps edge services (detector+processor+connector+policy+executor+console), steady state | ≤ 0.5 vCPU average, ≤ 512 MiB RSS total | DEFAULT, H5 |
| Prometheus | ≤ 1 GiB RSS at 7-day retention in the lab | DEFAULT |
| Inference latency per window | p95 < 1 s | DEFAULT |
| Detection (core faults F01, F02, F08) | event recall ≥ 0.80, precision ≥ 0.70, ≤ 1 false alarm per node-hour; else report and explain | DEFAULT |
| Predictive | lead time ≥ 10 min on F17/F18, ETA error reported | DEFAULT |
| RCA | Top-3 measured against B0/B1; target stated before final run | DEFAULT |
| Remediation safety | 0 unauthorized executions in negative suite | LOCKED |
| Offline | 0 duplicate incidents/commands after reconnect in tested cycles | LOCKED |
| Reproducibility | environment, configs, fault scripts, dataset manifest, analysis scripts versioned | LOCKED |

## 10. Data model (central PostgreSQL; indicative, Alembic is the source of truth)

| Table | Key columns |
|---|---|
| `tenants` | id, name (single row in MVP) |
| `users`, `memberships`, `sessions` | id, tenant_id, email, password_hash, role; session id hash, expiry |
| `sites` | id, tenant_id, name, status, last_heartbeat_at, cert_fingerprint, policy_version |
| `site_certificates` | id, site_id, serial, not_after, revoked_at |
| `enrollment_tokens` | id, site_id, token_hash, expires_at, used_at |
| `nodes`, `workloads` | id, site_id, k8s_uid, role/kind, labels |
| `events` | id, tenant_id, site_id, event_id, type, entity_ref, severity, occurred_at, received_at, payload JSONB; unique (site_id, event_id) |
| `incidents` | id, tenant_id, status, severity, fingerprint, opened_at, resolved_at |
| `incident_links` | incident_id, site_id, local_incident_id, last_version |
| `incident_state_history` | incident_id, from, to, actor, at (append-only) |
| `investigations`, `investigation_steps`, `tool_calls`, `evidence` | ids, incident_id, tool, args_hash, bounded result ref, model/prompt versions |
| `remediation_proposals`, `approvals`, `commands`, `executions`, `verifications` | ids, action_id/version, target_uid, params_hash, policy_version, requester, approver, expires_at, states |
| `audit_events` | id, actor, action, subject, at, details (append-only role) |
| `knowledge_docs`, `embeddings` | P1 RAG |
| `models` | id, model_id, version, feature_schema_version, sha256, promoted_at |
| `jobs` | transactional job/outbox table for the worker |

Every tenant-owned table has `tenant_id` from day one. RLS policies are added in P1 with cross-tenant tests.

Edge SQLite: `local_events`, `local_incidents (version)`, `outbox`, `commands`, `executions`, `policy_snapshot`, `sync_cursor`.

## 11. API contracts

Operator API `/api/v1` (session cookie + CSRF): `auth/session`, `auth/logout`, `sites`, `sites/{id}/nodes`, `events`, `incidents`, `incidents/{id}/investigations`, `investigations/{id}/evidence`, `remediations` (+`/{id}/approve`, `/{id}/reject`), `policies`, `audit`, `stream` (SSE).

Edge API `/edge/v1` (mTLS): `POST enrollment`, `POST heartbeat`, `GET config`, `GET policies/active`, `POST events/batch`, `POST incidents/batch`, `POST telemetry/summaries`, `GET commands?wait=25&lease=60`, `POST commands/{id}/ack|status|result`.

Limits (DEFAULT, load-test): heartbeat ~32 KB, event batch ~200 records/~1 MB, command ~64 KB, SSE metadata only (client refetches via REST). SSE: persistent notification records + cursor; on expired replay send reset; no tokens in URLs.

Schemas: `contracts/schemas/*.json`. Any schema change follows `WORKFLOW.md` §6.

## 12. Security and risks

Principles: least privilege everywhere; AI reasoning separated from write authority; central and edge trust boundaries independent; fail closed on expired policy; audit everything sensitive.

Kubernetes RBAC: `aiops-observer` (get/list/watch on nodes, namespaces, pods, deployments, replicasets, services, endpoints, events; bounded `pods/log`; **no** secrets, exec, port-forward, patch), `aiops-remediation-executor` (namespace-scoped get/patch on allowlisted Deployments and `deployments/scale`; nothing else), `aiops-telemetry` (scrape only). `automountServiceAccountToken: false` where unneeded.

Required security tests (live in `tests/security`): tenant leakage; expired/revoked cert rejected; site-id/cert mismatch rejected; observer cannot read secrets/exec/patch; executor limited to allowlist; modified approval rejected; expired and duplicate commands not re-executed; expired policy disables auto-remediation; prompt injection in logs creates no privileged action; credentials absent from logs and LLM payloads; critical actions produce full audit.

| Risk | Mitigation |
|---|---|
| Scope creep | Tiers in PRD §5; ADRs for any promotion |
| Research data too late | Healthy soak from S2; run metadata from first fault |
| Rules solve all faults, LLM adds nothing | Extended faults F11-F16 (rollout, config, image, dependency, limits, misleading log) |
| LLM unsupported RCA | Evidence refs, unsupported-claim metric, `inconclusive` allowed |
| Edge VM overloaded | Early measurement against §9 budget; resource limits in Helm |
| Poll latency | Long-poll channel; measure |
| Integration slips | Vertical slice by S3; joint demo every 2 sprints |
| No buyer | Interviews + kill/pivot rule |

## 13. Deployment and lab

Central: `deploy/compose/compose.yaml` (proxy, api, worker, postgres). Edge: `deploy/helm/edge-stack` with `values.schema.json`; pinned image digests; resource requests/limits on gateway services. Lab: `deploy/lab/` QEMU/libvirt scripts — server VM (2 vCPU, 3-4 GB), worker VM (2 vCPU, 2-3 GB), optional plain Linux VM; private network 192.168.100.0/24 (adapt if it conflicts). Fault injection only inside the disposable lab and namespace `aiops-test`. K3s versions pinned; server upgraded before agents.
