# ADR-0007: Isolation Forest is the primary candidate, not a settled choice

- Status: Accepted
- Date: 2026-11-02
- Owner: Student B

## Context
The master spec marked IF as FINAL in one place and "candidate only" in another.

## Decision
IF is the primary candidate (H1). Baselines ML-B0 and ML-B1 are mandatory, LOF is P1. Features are ratio-normalised with a `node_role` feature; per-role scaling is the fallback if pooled performance is poor.

## Consequences
Results decide the final detector; a negative result is reportable.
