# ADR-0002: Outbound-only site communication with long-poll command channel

- Status: Accepted
- Date: 2026-11-02
- Owner: Student A

## Context
Sites sit behind NAT/firewalls; central must never open inbound connections. Diagnostic tool calls are interactive (an investigation makes up to ~12), so plain periodic polling would add the poll interval to every call.

## Options considered
1. Fixed-interval polling: simplest; adds seconds per tool call.
2. Long-poll `GET /edge/v1/commands?wait=25`: still plain HTTPS/mTLS; near-instant delivery.
3. Persistent WebSocket/gRPC stream: lowest latency; more moving parts.

## Decision
Long-poll with a lease for MVP. Revisit a stream only if measured p50 diagnostic round-trip exceeds 2 s on the lab LAN.

## Consequences
Command delivery semantics stay at-least-once with leases and idempotency keys. Latency must be measured and reported.
