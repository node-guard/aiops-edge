# Product Requirements Document: Agentic AIOps for Edge Environments

| | |
|---|---|
| Status | Baseline v1.0 (trimmed scope) |
| Date | 2026-11-02 |
| Team | Two-person ING4 Software Engineering PFE (Student A: central + AI, Student B: edge + ML) |
| Horizon | ~5-6 months, 12 two-week sprints (see `BACKLOG.md`) |
| Source | Derived from the Master Project Specification v1.0 after the scope review; the trimmed tiers here override the original P0 list |

## 1. Vision

An operations platform for distributed Linux/K3s sites in which **local intelligence keeps monitoring and bounded recovery alive when the central link is down**, while **evidence-grounded AI investigation and fleet coordination** are available centrally. The AI never holds infrastructure write power: it proposes typed actions, and independent policy engines decide.

Official subject (Dellal-Hedjazi Badiâa): design and develop an agentic AIOps system able to identify anomalies in real time, handle them, then measure the results to reduce impact on performance, covering anomaly detection, root-cause analysis, **predictive analytics** and intelligent automation, in an Edge Computing context.

## 2. Problem

- Incidents span hosts, containers, Kubernetes, applications and network; diagnosis is manual correlation by specialists.
- Remote sites have constrained resources and unreliable links; a central-only design loses visibility and control exactly when needed.
- Unrestricted automated remediation (or an LLM with cluster credentials) is an unacceptable risk.

## 3. Users

| Persona | Goal | Key capabilities (MVP) |
|---|---|---|
| Operator | Understand and resolve incidents | See sites/incidents, read RCA, propose remediation |
| Approver | Authorize sensitive (L2) actions | Review exact action, target, parameters, evidence, expiry; approve/reject |
| Viewer / Auditor | Review history | Read incidents, evidence, executions, audit |
| Local Site Operator | Inspect a site while central is unreachable | Read-only local console |
| Admin (implicit) | Seed users and sites | CLI/seed scripts only; no admin UI in MVP |

## 4. Goals and non-goals

### Goals
1. A reproducible end-to-end incident lifecycle: detect → incident → investigate → propose → (approve) → act → verify → report.
2. Measured evidence for five hypotheses H1–H5 (`EXPERIMENTS.md`).
3. Safe-by-construction remediation proven by a negative test suite.
4. Offline autonomy that demonstrably works and re-syncs idempotently.
5. A labelled, reproducible Edge/K8s fault dataset and harness.

### Non-goals (MVP)
Managing PLCs/industrial devices; Windows hosts; HA K3s; multi-agent AI; local LLM (stretch only); tracing; Loki at every site; central TSDB; OIDC/Keycloak; multi-tenant admin UI; SBOM/signing/backup drills (design docs only); automatic model retraining.

## 5. Scope tiers (authoritative)

| Tier | Contents |
|---|---|
| **Must build (M)** | One K3s site in QEMU lab; Prometheus stack; node-level detector (IF + threshold + MAD/EWMA baselines); predictive exhaustion module; local event processor, SQLite outbox, Site Connector with mTLS; autonomy matrix + local policy engine + executor (ACT-001/002); central FastAPI + worker + PostgreSQL; LangGraph investigation agent with read-only tools; Remediation Manager with L0–L3 + approval; 3-page web dashboard; one-page Local Console; offline Scenario B; experiment harness and core experiments |
| **Simplified (S)** | Single tenant with `tenant_id` column (RLS as a P1 test); session auth with local users (argon2) and roles instead of OIDC; 3 dashboard pages; Local Console as one static page; OTel Collector dropped (Prometheus + bounded `kubectl logs` through observer RBAC) |
| **Should (P1)** | ACT-003 rollback (promoted: pairs with the bad-rollout fault); RAG over curated runbooks; second site; RLS enforcement tests; LOF baseline; Raspberry Pi/ARM worker run |
| **Design only (D)** | SBOM + signing, backup/restore drills, canary rollout, multi-tenant admin, OIDC integration, HA |

## 6. User stories and acceptance criteria

Format: Given / When / Then. Tier in brackets.

- **US-01 Observe [M].** Given a site is enrolled, when CPU stress runs on the worker, then Prometheus shows the metric and the detector emits `node.anomaly.detected` within the detection-latency target, carrying model id/version, feature-schema version and top contributing features.
- **US-02 Predict [M].** Given a slow memory leak or disk fill, when the trend would exhaust the resource within the configured horizon, then `node.resource.exhaustion_predicted` is raised with estimated time-to-exhaustion, before the resource is exhausted.
- **US-03 Incident [M].** Given related events within a window on the same entity hierarchy, when the local processor correlates them, then one incident is created and an outbox record is written in the same SQLite transaction.
- **US-04 Sync [M].** Given incidents/events in the outbox, when the connector uploads over mTLS, then central acknowledges per item, duplicates are acknowledged without duplication, and a stale version is ignored.
- **US-05 Investigate [M].** Given an incident, when an operator (or auto-trigger) starts an investigation, then the agent calls only allowlisted read-only tools, stores each tool call and evidence, and outputs a structured RCA with facts, hypotheses, alternatives, missing evidence and limitations; no unsupported claim is stated as fact.
- **US-06 Propose [M].** Given an RCA, when the agent proposes an action, then the proposal contains only a catalogue action ID and typed parameters; anything else is rejected before storage.
- **US-07 Approve [M].** Given an L2 proposal, when an approver (not the requester) approves the exact payload, then a command is issued with expiry; if parameters or target change afterwards, the approval is invalid.
- **US-08 Act and verify [M].** Given a valid command, when the site executes ACT-001/002, then the local policy engine re-checks it, execution is idempotent, and verification confirms recovery from independent service health (15 s checks, ≥2 min healthy), recorded separately from operation success.
- **US-09 Offline autonomy [M].** Given central is unreachable, when a fault occurs, then the site keeps detecting, creates local incidents, executes eligible L1 actions only while the cached policy is valid, keeps L2 pending, and syncs once on reconnection with no duplicates.
- **US-10 Local console [M].** Given central is unreachable, when a local operator opens the console, then they see current local health, incidents, action history, policy validity, connector state and last successful sync, and can change nothing.
- **US-11 Operator UI [M].** Given a logged-in operator, when they open the dashboard, then they see sites with CONNECTED/DEGRADED/OFFLINE/UNKNOWN status, an incident list, and an incident detail page with timeline, RCA, evidence, remediation and verification, updated live via SSE.
- **US-12 Security rejection [M].** Given the Scenario C attacks (foreign site id, observer secret read, out-of-allowlist action, replayed/expired command, edited approval, prompt injection in a log), then each is rejected, no write occurs and an audit record exists.
- **US-13 Impact report [M].** Given a resolved incident, then a report shows time-to-detect, time-to-recover and the action taken, and whether recovery was verified.
- **US-14 Feedback [S].** Given an RCA, when an operator marks it correct/incorrect, then the verdict is stored and only operator-validated incidents become retrievable history for the agent.
- **US-15 Rollback [P1].** Given a bad rollout fault, when the agent proposes ACT-003, then it requires L2 approval and verifies recovery.

## 7. Functional requirements

IDs carry over from the master spec; tier replaces the old priority.

| ID | Requirement | Tier |
|---|---|---|
| FR-01 | Register a site and issue a unique identity (seed script + enrollment token) | M |
| FR-02 | Collect Linux node and selected Kubernetes/workload metrics locally | M |
| FR-03 | Node-level features and shared per-site detector; baselines B0/B1/B2 | M |
| FR-03b | Predictive exhaustion forecasting for disk and memory | M |
| FR-04 | Normalize, fingerprint, deduplicate, correlate events locally | M |
| FR-05 | Persist incidents and outbox records atomically | M |
| FR-06 | Sync events, incidents, heartbeats and results over outbound mTLS | M |
| FR-07 | Central fleet/sites/nodes/incidents/investigations views | M |
| FR-08 | One central evidence-grounded investigation agent, read-only tools | M |
| FR-09 | Propose only catalogue action IDs with typed parameters | M |
| FR-10 | Evaluate permission, policy, exact target, approval and expiry before dispatch | M |
| FR-11 | Execute ACT-001/002 with restricted RBAC | M |
| FR-12 | Verify operation-level and application-level recovery separately | M |
| FR-13 | Autonomy matrix drives local L1 decisions; fail closed on expired policy | M |
| FR-14 | Authenticated read-only Local Console | M |
| FR-15 | Tenant-filtered SSE notifications (single tenant in MVP) | M |
| FR-16 | Multi-site correlation and two lab sites | P1 |
| FR-17 | ACT-003 rollback with approval | P1 |
| FR-18 | Operator RCA feedback loop | S |
| FR-19 | Per-incident impact report | M |

## 8. Non-functional requirements

| Quality | Requirement |
|---|---|
| Security | Server-side sessions, per-site mTLS, least-privilege K8s identities, strict remediation policy, full audit; no secrets in logs/LLM context |
| Reliability | At-least-once delivery, idempotent consumers, transactional outbox |
| Performance | Measure and report: detection latency, investigation latency, inference latency, API latency; no unverified SLA |
| Edge footprint | Declared budget in `SPEC.md` §9 (H5); measured, reported |
| Auditability | Actor, request, policy version, approval, command, execution, verification persisted |
| Usability | Explicit CONNECTED/DEGRADED/OFFLINE/RECONNECTING/SYNCING/UNKNOWN; never colour-only status |
| Reproducibility | Versioned environment, fault scripts, dataset manifest, analysis scripts |

## 9. Success metrics

**Research (frozen before final evaluation, S11):** detection event recall/precision and false alarms per node-hour; Top-1/Top-3 RCA vs baselines; MTTR vs manual and native-Kubernetes baselines; zero unauthorized executions in the negative suite; zero duplicate processing after reconnect; resource budget respected.

**Product validation (parallel, not gating the PFE; script in `docs/discovery/interview-script.md`):** 8–10 discovery interviews, ≥3 incident walkthroughs, ≥1 design-partner conversation. Kill/pivot rule: after 5 interviews, if fewer than 2 operate multi-site Linux infrastructure, revisit the segment.

## 10. Release plan

Milestones P0–P10 map to sprints S1–S12 (`BACKLOG.md`). Demo-able increment every sprint; integration demo every second sprint; first full vertical slice (event → central dashboard) by end of S3; complete lifecycle by S9; Scenario B by S10.

## 11. Risks

See `SPEC.md` §12 and the master risk register. Top three: scope creep (mitigate with tiers and `docs/adr`), research data collected too late (healthy-data soak from S2), LLM unsupported claims (evidence refs + unsupported-claim metric).

## 12. Open questions

| Question | Owner | Needed by |
|---|---|---|
| PFE defense date and sprint length confirmation | Both | S1 |
| Supervisor: does "Edge" imply real devices (Raspberry Pi/ARM)? | Both | S1 |
| University/supervisor IP and commercialization terms | Both | S4 |
| LLM provider, budget and key handling (cloud API; local fallback stays stretch) | Student A | S7 |
| Product positioning: MSPs vs "teams without ops staff" (align deck and spec) | Both | S6 |

## 13. Traceability to the official subject

| Official subject | Where addressed |
|---|---|
| Observe / engage / act | SPEC §3, workflow in ARCHITECTURE |
| Anomaly detection | SPEC §5, US-01 |
| Root-cause analysis | SPEC §7, US-05 |
| Predictive analytics | SPEC §5.4, US-02 |
| Intelligent automation | SPEC §8, `AUTONOMY_MATRIX.md`, US-08/09 |
| Generative + agentic AI | SPEC §7 (agent investigates, proposes; policy executes) |
| Measure results to reduce impact | US-13, H3, MTTR |
