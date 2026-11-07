# Agentic AIOps for Edge Environments

Master PFE project: an Edge-first AIOps platform. Local sites keep monitoring, anomaly detection, incident persistence and bounded recovery when the central link is down; a central platform runs an evidence-grounded LLM investigation agent and the approval flow. The AI never holds infrastructure write power.

## Start here
| If you want to... | Read |
|---|---|
| Understand the product and scope | [`docs/PRD.md`](docs/PRD.md) |
| Build against the technical contract | [`docs/SPEC.md`](docs/SPEC.md) |
| See diagrams | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Know what runs offline and who decides | [`docs/AUTONOMY_MATRIX.md`](docs/AUTONOMY_MATRIX.md) |
| Work with a coding agent | [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md), [`docs/WORKFLOW.md`](docs/WORKFLOW.md) |
| Pick the next task | [`docs/BACKLOG.md`](docs/BACKLOG.md) |
| Run experiments | [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md), [`docs/FAULT_MATRIX.md`](docs/FAULT_MATRIX.md) |
| Deploy the edge observability stack | [`deploy/helm/edge-stack/README.md`](deploy/helm/edge-stack/README.md) |
| See past decisions | [`docs/adr/`](docs/adr) |

## Quick start
```bash
cp .env.example .env     # fill local values; never commit
make setup               # uv sync, pre-commit
make check               # lint + types + tests + schemas + Helm chart render
make up                  # central stack (Docker Compose)
make lab-up              # QEMU/K3s lab (see deploy/lab/README.md)
```

## Repo layout
```text
contracts/      JSON schemas, examples, action catalogue, autonomy/policy YAML (source of truth)
docs/           PRD, SPEC, ARCHITECTURE, WORKFLOW, BACKLOG, ADRs, experiments
src/aiops/      contracts, common, central (api, worker, agent, remediation, db), edge (detector, processor, connector, policy, executor, console_api)
web/            React dashboard + local console page
deploy/         compose, helm edge-stack, QEMU lab scripts
experiments/    fault scripts, harness, analysis, run metadata
prompts/        agent prompts and injection tests
tests/          unit, integration, security, e2e
.claude/        slash commands and subagents for Claude Code
```

## Status
Baseline docs v1.0 (2026-11-02). Sprint status lives in `docs/BACKLOG.md`.

Supervisor guidance recorded 2026-11-06: the repository may stay public for now
and no license/CLA is required at this stage; the thesis may quote logs and
metrics. The exact June 2026 defense date, final publication/license terms and
evaluation expectations are reworked in Sprint 13 (`S13-J1`, `S13-J2`).

Sprint 2 is in progress: the edge observability stack (`S2-B1`) is installed and
verified in the lab; the healthy-data soak (`S2-B4`) starts next and must run
for at least five continuous days.

## Team
Student A (central + AI), Student B (edge + ML), supervisor Prof. Badiâa Dellal-Hedjazi.
