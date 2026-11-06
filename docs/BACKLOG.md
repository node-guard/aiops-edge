# Backlog: 12 two-week sprints

Single status board. Task ID format `S<sprint>-<owner><n>` where owner is **A** (central + AI), **B** (edge + ML) or **J** (joint). Status: `todo` · `doing` · `review` · `done` · `cut`. Tier from PRD §5: **M** must, **S** simplified, **P1** should, **D** design-only (a short doc, no code).

Rules: tasks ≤ 3 working days; split otherwise. Acceptance is demonstrable. The last sprint week of S11 is buffer. If a sprint slips by a third, cut by tier (see `WORKFLOW.md` §12).

## Sprint goals at a glance

| Sprint | Goal | Demo at the end |
|---|---|---|
| S1 | Foundation + lab | `make up` healthy central; lab workload reachable |
| S2 | Observability + data collection starts | CPU stress visible in Prometheus; soak running |
| S3 | Event + incident pipeline (**vertical slice**) | Injected event appears in central, duplicate-safe |
| S4 | ML detector + predictive module | F01/F02 raise anomaly event with versions; F17 predicts |
| S5 | Site identity (mTLS) | Enroll, heartbeat, revoked cert rejected |
| S6 | Auth + dashboard core + local console | Operator sees live incident from the site |
| S7 | Command channel + diagnostic tools | Real diagnostics through the channel, latency measured |
| S8 | LangGraph agent + RCA (+ RAG P1) | Evidence-backed RCA on a real incident; injection test |
| S9 | Remediation | F02 → ACT-001 verified; unauthorized action rejected |
| S10 | Offline autonomy | Scenario B end-to-end |
| S11 | Integration, hardening, freeze | Scenarios A/B/C automated; criteria frozen |
| S12 | Evaluation + thesis | Final runs, analysis, release candidate |

---

## S1: Foundation and lab
Goal: both students can run central and the lab; contracts v1 frozen.

| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S1-J1 | Create repo from this pack; CI green; pre-commit; CODEOWNERS handles set | M | J | `make check` green locally and in CI | todo |
| S1-J2 | Review and freeze contracts v1 (event, incident, command, rca, run-meta) | M | J | `make schemas` green; examples valid; both approve | done |
| S1-J3 | Confirm with supervisor: defense date, edge-device expectation (RPi/ARM), IP rules | M | J | Answers recorded in PRD §12 | todo |
| S1-J4 | Prepare interview script; book 3 interviews | S | J | Script in `docs/discovery/`; 3 slots booked | todo |
| S1-B1 | QEMU/libvirt scripts: server + worker VM, private net, K3s install, kubeconfig fetch | M | B | `make lab-up` yields 2 Ready nodes; API private | done |
| S1-B2 | Sample app `shop-demo` (HTTP + health + DB dependency) deployed in `aiops-test` | M | B | App reachable from host; health endpoint works | done |
| S1-A1 | Central Compose: proxy, API skeleton (`/health/live|ready|dependencies`), PostgreSQL | M | A | `make up` → all healthy | done |
| S1-A2 | Alembic baseline + base models (`tenants`, `sites`, `users`) | M | A | `alembic upgrade head` on empty DB passes | done |

## S2: Observability and data collection
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S2-B1 | Helm `edge-stack` v0: Prometheus, node-exporter, kube-state-metrics, Alertmanager; resource limits | M | B | Node/pod metrics visible; values schema validates | todo |
| S2-B2 | Experiment harness v0: `run_fault.py`, `meta.json`, lab-context guard; faults F01, F02 | M | B | Run produces meta + labelled window | todo |
| S2-B3 | Workload generator (Locust) for realistic healthy variation | M | B | Variable load profile documented | todo |
| S2-B4 | Healthy-data soak started (≥ 5 days continuous) | M | B | Prometheus retention proof; notes in `experiments/NOTES.md` | todo |
| S2-B5 | Prometheus → Parquet export for feature windows (script) | M | B | Parquet with units, no zero-filled gaps | todo |
| S2-A1 | DB schema v1: events, incidents, incident_links, state history, audit | M | A | Migration + repository tests | todo |
| S2-A2 | Tenant-aware repository layer (tenant arg required) + lint test | M | A | Test fails if a query omits tenant | todo |
| S2-J1 | Conduct interviews 1-3 | S | J | Notes logged, anonymized | todo |

## S3: Event and incident pipeline (vertical slice)
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S3-B1 | Local event processor: normalize, fingerprint, dedupe, correlate (time + hierarchy) | M | B | Unit tests with fixture event streams | todo |
| S3-B2 | SQLite store + transactional outbox (events + incident versions in one tx) | M | B | Crash test: kill process mid-write, no partial state | todo |
| S3-B3 | Connector v0 (HTTPS, no mTLS yet): batching, item acks, backoff | M | B | Duplicate batch acknowledged, no duplicates central | todo |
| S3-A1 | Central ingestion `POST events/batch`, `incidents/batch` with idempotency and version rules | M | A | Duplicate ack / stale ignore / conflict reject + audit | todo |
| S3-A2 | Incident state machine + append-only history | M | A | Illegal transitions rejected; tests | todo |
| S3-J1 | Edge↔central contract tests from `contracts/examples` | M | J | CI job green | todo |
| S3-J2 | Supervisor checkpoint 1 (vertical slice demo) | M | J | Demo done, feedback logged | todo |

## S4: ML detector and predictive module
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S4-B1 | Feature pipeline (1m/5m windows), ratio features + `node_role`, schema v1 | M | B | Feature-schema.json versioned; tests on gaps/resets | todo |
| S4-B2 | Baselines ML-B0 threshold, ML-B1 MAD/EWMA | M | B | Evaluated on first labelled runs | todo |
| S4-B3 | Isolation Forest training protocol + model package (manifest, SHA256SUMS) | M | B | Package loads and verifies hash | todo |
| S4-B4 | Detector service: 30 s inference, emits `node.anomaly.detected` with `top_features` and versions | M | B | F01/F02 produce events end-to-end into central | todo |
| S4-B5 | Predictive module: disk/memory time-to-exhaustion, event `node.resource.exhaustion_predicted` | M | B | F17 predicts with ≥ 10 min lead (pilot) | todo |
| S4-B6 | Faults F03, F04, F17, F18 scripted | M | B | Harness runs them | todo |
| S4-J1 | Freeze resource budget (H5) and draft detection targets in SPEC §9 | M | J | PR merged; hash recorded | todo |
| S4-A1 | Central stores model metadata; shows on anomaly events | S | A | `models` table populated | todo |
| S4-J2 | Interviews 4-5; apply kill/pivot rule | S | J | Decision logged | todo |

## S5: Site identity (mTLS)
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S5-A1 | Mini-CA + enrollment tokens (single-use, hashed) + CSR endpoint | M | A | Site gets cert; token reuse rejected | todo |
| S5-A2 | Site registry, revocation list, heartbeat status (CONNECTED/DEGRADED/OFFLINE/UNKNOWN) | M | A | Status transitions tested | todo |
| S5-B1 | Connector: local key + CSR, mTLS to central, heartbeat, cert rotation basics | M | B | Private key never leaves site (test) | todo |
| S5-J1 | Security tests: revoked/expired cert rejected; payload site_id ≠ cert rejected | M | J | `make test-sec` green | todo |
| S5-A3 | Derive tenant/site from cert in every edge endpoint | M | A | Test with forged payload fails | todo |

## S6: Auth, dashboard core, local console
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S6-A1 | Session auth (argon2id, cookie, CSRF), roles operator/approver/viewer | S | A | Auth tests incl. fixation, expiry, CSRF | todo |
| S6-A2 | SSE notifications with persistent records + cursor + reset | M | A | Replay + reset tested | todo |
| S6-A3 | React shell + pages: Overview (sites/nodes), Incidents list, Incident detail (timeline) | M | A | Playwright smoke: live incident appears | todo |
| S6-B1 | Local Console v0: single read-only page via `console_api` | M | B | Shows health, incidents, policy status, last sync; no write controls | todo |
| S6-J1 | Reconcile product positioning (MSP vs teams without ops staff); align deck and PRD | S | J | Decision recorded | todo |
| S6-J2 | Interviews 6-7; supervisor checkpoint 2 | S | J | Notes + feedback | todo |

## S7: Command channel and diagnostic tools
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S7-A1 | Command service: envelope, long-poll `GET commands`, leases, ack/status/result | M | A | Duplicate/expired handling tested | todo |
| S7-A2 | Diagnostic gateway: typed tool wrappers, validation, size caps | M | A | Invalid args rejected before dispatch | todo |
| S7-B1 | Connector command handler + diagnostic runner with observer ServiceAccount | M | B | 10 tools return bounded data from the lab | todo |
| S7-B2 | Observer RBAC + NetworkPolicy + negative tests (no secrets/exec/patch) | M | B | Security tests green | todo |
| S7-J1 | Measure diagnostic round-trip latency (p50/p95) | M | J | Report in `experiments/NOTES.md`; ADR-0002 check | todo |
| S7-A3 | LLM provider interface + key handling + redaction layer | M | A | Redaction unit tests; no secrets in payload | todo |

## S8: LangGraph agent, RCA, RAG
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S8-A1 | LangGraph graph: bounded steps/time/tokens, tool selection, evidence store | M | A | Run on F01/F08 produces tool-call trail | todo |
| S8-A2 | Structured RCA output + unsupported-claim check + `inconclusive` path | M | A | Output validates against `rca-report.v1`; timeout returns inconclusive | todo |
| S8-A3 | Prompt-injection hardening and test suite (`prompts/injection-tests.md`) | M | A | F16 passes; no privileged action | todo |
| S8-A4 | RAG over curated runbooks (≥ 10) + operator-validated incidents | P1 | A | Retrieval tenant-filtered | todo |
| S8-B1 | RCA baselines: B0 rules + topology, B1 one-shot LLM | M | B | Runnable on stored incidents | todo |
| S8-B2 | Faults F05-F10 and extended F11-F16 scripted | M | B | Harness runs them | todo |
| S8-J1 | First RCA experiment pass (pilot 2-3 runs per fault) | M | J | Results table committed | todo |

## S9: Remediation
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S9-A1 | Remediation Manager: proposal validation, L0-L3, approver ≠ requester, expiry, params hash | M | A | State machine tests | todo |
| S9-A2 | Approval UI in incident detail (exact payload, evidence, expiry) | M | A | Playwright: approve/reject flow | todo |
| S9-B1 | Local policy engine + policy snapshot with expiry + autonomy.yaml loader | M | B | Matrix tests match `AUTONOMY_MATRIX.md` | todo |
| S9-B2 | Executor SA + ACT-001/ACT-002, idempotent, execution records | M | B | Duplicate command does not repeat | todo |
| S9-B3 | Verification loop (15 s, ≥ 2 min healthy, 5 min max) | M | B | Verified vs operation-success separate | todo |
| S9-J1 | Negative test suite (Scenario C list) | M | J | All rejections + audit | todo |
| S9-J2 | Impact report per incident | M | A | Report visible on resolved incident | todo |
| S9-J3 | Supervisor checkpoint 3 (full lifecycle) | M | J | Demo + feedback | todo |

## S10: Offline autonomy
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S10-B1 | Local rule → action mapper (playbook) + cooldown/rate limits | M | B | Fingerprint→action tests | todo |
| S10-B2 | Fail-closed on policy expiry and clock drift | M | B | Tests for expiry/drift | todo |
| S10-B3 | Offline operation: outbox growth caps, priority rules, reconnect sync | M | B | 2-hour outage test passes | todo |
| S10-A1 | Central reconciliation after reconnect; dashboard shows stale/last sync | M | A | No duplicates central | todo |
| S10-J1 | Scenario B end-to-end incl. netem intermittent link | M | J | Automated test + recorded demo | todo |
| S10-B4 | ACT-003 rollback (L2) + F11 | P1 | B | Rollback verified after bad rollout | todo |
| S10-A2 | Operator RCA feedback (correct/incorrect) feeding validated history | S | A | Stored and used by RAG filter | todo |

## S11: Integration, hardening, freeze
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S11-J1 | Automate scenarios A, B, C in `tests/e2e` | M | J | CI/nightly run on lab | todo |
| S11-B1 | Resource measurement vs budget (H5) | M | B | Report with CPU/RAM/inference | todo |
| S11-A1 | RLS enforcement + cross-tenant tests | P1 | A | Tests green | todo |
| S11-J2 | Security review; log/LLM redaction tests; threat-model update | M | J | `make test-sec` green; doc updated | todo |
| S11-J3 | Design-only docs: backup/restore, SBOM/signing, canary rollout (1-2 pages each) | D | J | Docs in `docs/design/` | todo |
| S11-J4 | **Freeze evaluation criteria and targets**; record commit hash | M | J | Tag `eval-freeze` | todo |
| S11-J5 | Interviews complete (8-10); design-partner ask | S | J | Summary doc | todo |
| S11-J6 | Buffer (last 3 days): fix, polish, cut | M | J | n/a | todo |

## S12: Evaluation and thesis
| ID | Task | Tier | Owner | Acceptance | Status |
|---|---|---|---|---|---|
| S12-J1 | Final experiment runs (≥ 10 valid reps per core scenario) | M | J | `runs/index.parquet` complete | todo |
| S12-J2 | Analysis notebooks and statistics (paired, effect sizes) | M | J | Figures regenerate from scripts | todo |
| S12-J3 | Dataset manifest + reproducibility package | M | J | Fresh clone reproduces key figures | todo |
| S12-J4 | Thesis writing, demo video, release candidate tag | M | J | `v1.0-rc` | todo |
| S12-J5 | Optional: Raspberry Pi/ARM worker run | P1 | B | Reported if done | todo |

## Parking lot (not scheduled)
Local LLM experiment; OIDC; multi-site correlation; second lab site; LOF baseline; workload-specific models; central TSDB.
