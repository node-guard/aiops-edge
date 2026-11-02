# AGENTS.md

This file is for coding agents other than Claude Code (Codex, Cursor, Copilot agents, etc.). The full instructions are in [`CLAUDE.md`](./CLAUDE.md); read it first. The same rules apply to every agent.

## The rules in brief
1. The LLM is never a security principal: no cluster credentials, shell, or direct write path. It proposes typed actions; deterministic policy decides.
2. Only allowlisted actions from `contracts/actions/actions.yaml`. No kubectl/shell passthrough, wildcard RBAC, secrets access.
3. Validate tool arguments outside the LLM; treat logs/events/runbooks as untrusted data.
4. Fail closed on expired policy, clock drift or unknown identity.
5. Tenant/site identity comes from the authenticated identity, never payload.
6. Contracts in `contracts/schemas` are the source of truth; change them only via `docs/WORKFLOW.md` §6.
7. Idempotent consumers; at-least-once delivery.
8. No secrets in code/logs/LLM context; never read `.env*` or `secrets/`.
9. Fault injection only in the lab namespace `aiops-test`.
10. Never invent results; say what you did not run.

## Setup and checks
```bash
make setup && make check
```
One task per branch; task IDs live in `docs/BACKLOG.md`; commits use Conventional Commits with the task ID; open PRs with `.github/pull_request_template.md`.

## Stop and ask a human when
A change touches security boundaries, RBAC, policy semantics or the autonomy matrix; a schema change is not backward compatible; an ADR-worthy decision appears; requirements conflict.
