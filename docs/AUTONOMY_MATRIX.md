# Autonomy Matrix (authoritative)

Answers: who decides, what triggers an action, and what is allowed offline. The machine-readable form is `contracts/policies/autonomy.yaml`; keep both in sync (a unit test compares `actions.yaml` with `autonomy.yaml` for action IDs and levels).

## Principles

1. **The policy decides, not the source.** An action's level is the same whether a local rule or the central agent triggers it. The agent can only *propose*.
2. Local rules (the "playbook") map a **fingerprint of conditions** to a **proposed action**, then the local policy engine checks scope, cooldown and policy validity.
3. Offline, only L1 decisions that pass the checks may execute. L2 waits. L3 is rejected always.
4. Expired, invalid or unreachable policy, or clock drift beyond tolerance → automatic remediation disabled (observation and incident persistence continue).

## Actions

| Action | Operation | Level rule | Default trigger | Offline? |
|---|---|---|---|---|
| ACT-001 | Restart an allowlisted stateless Deployment (rollout annotation) | **L1** in `aiops-test`, on allowlisted target, within cooldown and rate limit | Local rule: `app.health_check.failed` (F08) or `workload.memory_pressure` (F02) on the target; or central agent proposal. CrashLoopBackOff/OOMKilled/ImagePull/dependency failures are **not** local triggers (restarting does not fix them, F12-F15) | Yes, while cached policy valid |
| ACT-002 | Scale an allowlisted Deployment | **L1** only for scale-out of **+1 replica** up to `max_replicas`; **L2** for scale-in or any larger change | Local rule: sustained CPU saturation on the workload's node plus workload latency/health degradation; or agent proposal | L1 case yes; L2 waits |
| ACT-003 | Roll back Deployment to previous revision (P1) | **L2 always** | Agent proposal after bad-rollout RCA | No (needs approval) |
| any other | shell, kubectl, delete, patch outside allowlist | **L3** | n/a | Rejected |

## Local limits (DEFAULT, in policy snapshot)

| Limit | Value |
|---|---|
| Allowed namespaces | `aiops-test` |
| Cooldown per target | 10 min |
| Max L1 actions per target per hour | 2 |
| Max L1 actions per site per hour | 6 |
| Command expiry | 5 min after issue |
| Policy snapshot validity | 24 h, refreshed on every successful sync |
| Clock-skew tolerance | 30 s |

## Decision table (what the local engine does)

| Condition | Result |
|---|---|
| Valid policy, L1 action in scope, cooldown clear | Execute, verify, record |
| Valid policy, action needs L2 | Create pending approval; central connected → notify approver; disconnected → stay pending, never auto-approve |
| Policy expired / invalid / missing | Disable automatic remediation; record `policy_expired`; keep detecting |
| Target not allowlisted or UID mismatch | Reject, audit |
| Duplicate command id | Return recorded result, do not re-execute |
| Expired command | Reject (`410`), audit |
| Cooldown or rate limit hit | Skip, record reason, escalate incident |

## Expected behaviour per fault (see `FAULT_MATRIX.md`)

The agent must also learn **restraint**: for dependency outages (F14) and limit-induced OOM (F15) a restart is the wrong fix; the correct output is RCA plus escalation, and the evaluation counts an unnecessary action as an error.
