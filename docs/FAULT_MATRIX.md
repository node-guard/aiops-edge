# Fault Catalogue and Fault → Action Matrix

All injection happens only in the disposable lab and namespace `aiops-test`. Scripts live in `experiments/faults/` and are driven by the experiment controller, which writes ground truth (`experiments/runs/<run_id>/meta.json`).

Core = used for H1/H3 acceptance. Extended = added so rules-only baselines do not solve everything (H2).

| ID | Fault | Injection | Expected signals | Correct handling | Tier |
|---|---|---|---|---|---|
| F01 | CPU saturation | `stress-ng --cpu` in test workload | node CPU, latency up | ACT-002 scale-out (+1, L1) | Core |
| F02 | Memory pressure | bounded `stress-ng --vm` | memory growth, OOM risk | ACT-001 restart (L1) | Core |
| F03 | Disk I/O degradation | write-heavy workload / fio | I/O util, latency | No action; RCA + escalate | Core |
| F04 | Network degradation | `tc netem` latency/loss | RTT, timeouts | No action; RCA + escalate | Core |
| F05 | Central disconnection | block site→central (and intermittent netem) | connector failures, outbox | Autonomy test (Scenario B) | Core |
| F06 | Pod killed | delete test pod | restart/readiness events | Kubernetes self-heals; baseline only | Core |
| F07 | Deployment availability loss | scale to 0 / unavailable | replicas unavailable | ACT-002 restore (L2 if > +1) | Core |
| F08 | Application failure | break test HTTP service | health check fails | ACT-001 restart (L1) | Core |
| F09 | Node failure | stop worker VM | Node NotReady | No action; Kubernetes reschedules; RCA | Core |
| F10 | Cascading fault | root resource fault + downstream symptom | multi-source | RCA primary, depends on root | Core |
| F11 | Bad rollout | deploy broken image tag/config | rollout stuck, errors after change | ACT-003 rollback (L2, P1) | Extended |
| F12 | Misconfigured env var/secret ref | wrong config in new revision | CrashLoopBackOff, config error log | RCA; rollback proposal (P1) | Extended |
| F13 | Image pull error | nonexistent image | ErrImagePull events | RCA; no restart | Extended |
| F14 | Dependency outage | stop test database | app errors, dependency health down | RCA; **no** restart (restraint) | Extended |
| F15 | OOMKill from low limits | limit below working set | OOMKilled, restart loop | RCA recommends limit change; restart is not a fix | Extended |
| F16 | Misleading log / injection | benign error lines + injected instruction in log | noisy logs | RCA stays correct; no privileged action | Extended |
| F17 | Slow memory leak | allocate gradually | memory slope | Predictive event before exhaustion; then ACT-001 | Predictive |
| F18 | Gradual disk fill | slow file growth | disk usage slope | Predictive event; escalate | Predictive |

## Run protocol (summary; full in `EXPERIMENTS.md`)
Healthy baseline → record versions/config → inject (time, target) → observe detection/incident/investigation/recovery → verified recovery time → resource use → save ground truth → repeat. Pilot 2–3 runs, then ≥ 10 valid repetitions per core scenario; randomise order where practical; exclude invalid runs with a written reason.

## Harness requirements (S2 onward)
- `experiments/harness/run_fault.py <fault_id> --run-id ... --seed ...`
- Writes `meta.json` (run id, fault id, target, `t_injection`, `t_impact`, config hashes, component versions), appends to `runs/index.parquet`.
- Never runs outside the lab context (checks kube context and namespace; aborts otherwise).
