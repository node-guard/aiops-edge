# ADR-0011: Drop the OpenTelemetry Collector from the MVP

- Status: Accepted
- Date: 2026-11-02
- Owner: Student B

## Context
Prometheus covers metrics; logs are retrieved on demand with bounded `pods/log` through the observer role. The Collector adds a component and RAM without a MVP-critical role.

## Decision
No OTel Collector at the edge in MVP. Keep OpenTelemetry resource attribute naming conventions for identity. Reconsider if a log store or traces are added.

## Consequences
`search_application_logs` is filtered `pods/log` retrieval, with strict caps.
