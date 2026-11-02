# ADR-0004: Single tenant in MVP, `tenant_id` on every tenant-owned row

- Status: Accepted
- Date: 2026-11-02
- Owner: Student A

## Context
Multi-tenancy matters commercially (MSPs) but full RLS + admin UI is costly for a PFE.

## Decision
One seeded tenant; every tenant-owned table, query, cache key, SSE channel and vector filter carries `tenant_id` from day one. PostgreSQL RLS policies and cross-tenant tests are a P1 item (S11).

## Consequences
No retrofit of the schema later. Queries must always filter by tenant; a lint/test checks repository functions require a tenant argument.
