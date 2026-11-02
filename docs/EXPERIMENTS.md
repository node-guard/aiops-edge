# Experimental Evaluation Plan

Method: Design Science Research (problem, objectives, design, demonstration, evaluation, communication) plus controlled experiments. A feature demo is not evidence.

## Hypotheses

| ID | Statement | Baselines / comparison | Primary measures |
|---|---|---|---|
| H1 | At a comparable false-alert rate, Isolation Forest improves event-level detection over static thresholds on the testbed workloads | ML-B0 thresholds, ML-B1 MAD/EWMA, ML-B3 LOF (P1) | event precision/recall/F1, PR-AUC, false alarms per node-hour, detection delay, CPU/RAM |
| H1b | Forecasting raises a warning before exhaustion with useful lead time | `predict_linear` vs robust/Holt fit | lead time, ETA absolute error, false predictions per node-day |
| H2 | A tool-using LLM with structured evidence improves Top-k RCA over rules and one-shot LLM, especially on extended faults F11-F16 | RCA-B0 rules+topology, RCA-B1 one-shot LLM, RCA-B2 tool-using agent (+RAG when available) | Top-1/Top-3, fault-type accuracy, evidence coverage, unsupported-claim rate, tool calls, latency, cost, unnecessary-action rate |
| H3 | Policy-controlled bounded remediation reduces median time to verified recovery for supported faults without any unauthorized execution | manual (simulated operator with fixed reaction time, stated in advance), native Kubernetes (liveness probes, HPA), AIOps | time to verified recovery (MTTR), action success, verification failure, operator steps |
| H4 | During central loss, local observation, incident persistence and valid L1 actions continue; sync after reconnect is idempotent | connected vs disconnected vs reconnect; short, long (hours) and intermittent (netem) outages | local detection, L1 correctness, L2 wait, lost/duplicate records, sync delay, outbox size |
| H5 | The site detector and edge services stay within the declared resource budget | normal vs higher site workload | CPU, RAM, storage, inference latency |

## Definitions

```text
MTTR                    = t_verified_recovery - t_incident_impact
T_injection_to_detection = t_detection - t_injection
T_impact_to_detection    = t_detection - t_impact
```

## Dataset rules
- Primary: own QEMU/K3s dataset (Parquet) with run manifest. Supplementary: SMD, NAB, RCAEval, reported separately and never as a substitute.
- Split by time block or complete run; never randomly across overlapping windows.
- Thresholds chosen on validation data only.
- Each run keeps: raw Prometheus export for the window, events, incidents, tool calls, RCA JSON, remediation records, `meta.json`.

## Statistics
Report median, mean, dispersion, confidence intervals. Paired comparison when the same scenario is evaluated under several configurations; paired t-test only if assumptions hold, otherwise Wilcoxon signed-rank or bootstrap. Report effect sizes.

## Schedule
- S2: harness v0 + healthy soak starts. S4: first ML runs. S8: first RCA runs. S10: offline runs. S11: **freeze criteria and targets** (commit hash of `docs/SPEC.md` §9 recorded). S12: final runs, analysis, thesis figures.
- Failures and disproved hypotheses are valid results; report them.

## Run metadata schema
See `contracts/schemas/run-meta.v1.schema.json`.
