# ADR-0009: Autonomy matrix: the policy decides, not the trigger source

- Status: Accepted
- Date: 2026-11-02
- Owner: Both

## Decision
Action level and limits are properties of the action and context (see `docs/AUTONOMY_MATRIX.md`), not of who proposed it. Local rules propose; the policy engine authorizes. ACT-001 is L1; ACT-002 is L1 only for +1 scale-out within max, otherwise L2; ACT-003 is L2.

## Consequences
Offline behaviour is deterministic and testable; the agent cannot gain privilege by being the proposer.
