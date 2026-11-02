# ADR-0006: Deterministic Python policy engine (OPA deferred)

- Status: Accepted
- Date: 2026-11-02
- Owner: Both

## Decision
The central Remediation Manager and the local policy engine are plain, unit-tested Python driven by `contracts/actions/actions.yaml` and `contracts/policies/autonomy.yaml`. The LLM has no write path.

## Consequences
Policy logic is small enough to test exhaustively. If rules grow past what YAML + Python can express, write an ADR to evaluate OPA/Rego.
