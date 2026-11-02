---
description: Security review of the current diff against the project's non-negotiable rules
---
Review `git diff main...HEAD` against CLAUDE.md "Non-negotiable rules" and SPEC §12.
Check specifically: LLM write paths; action allowlist; argument validation outside the LLM; fail-closed behaviour; tenant/site derived from identity; idempotency; secrets in logs/fixtures/LLM payloads; RBAC widening; fault-injection guards.
Output: findings by severity with file:line, concrete failing scenario, and the test that should exist. Say explicitly what you could not verify.
