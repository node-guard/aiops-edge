# ADR-0001: Monorepo with one Python project and namespaced packages

- Status: Accepted
- Date: 2026-11-02
- Owner: Both

## Context
Two students, shared contracts, one coding agent working across central and edge code. Multiple repos would multiply version drift and coordination cost.

## Options considered
1. Multi-repo (central, edge, contracts): clean boundaries, high coordination overhead.
2. Monorepo with one `pyproject.toml` and packages `aiops.central`, `aiops.edge`, `aiops.contracts`, `aiops.common`: shared tests and schemas, one CI.

## Decision
Monorepo, one Python project (optional dependency groups `central` and `edge` so images stay small), `web/` as a separate Node project.

## Consequences
Single CI and one contract source. Images are built from the same repo with different extras. Directory ownership is enforced by CODEOWNERS rather than by repo boundaries.
