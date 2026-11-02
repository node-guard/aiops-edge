# ADR-0005: SQLite local store with transactional outbox, at-least-once delivery

- Status: Accepted
- Date: 2026-11-02
- Owner: Student B

## Decision
Edge state lives in SQLite (WAL). Incident versions and outbox records are written in one transaction. Delivery is at-least-once; consumers are idempotent using `(site_id, event_id)`, `(site_id, local_incident_id, version)` and `command_id`. Same id with different payload is a conflict and is audited.

## Consequences
Need a bounded outbox with retention, capacity alarm and priority rules; test long outages.
