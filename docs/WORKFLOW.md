# Working Agreement and Agent Workflow

How two students and one or two coding agents ship this project without stepping on each other.

## 1. Roles

| Role | Who | Owns |
|---|---|---|
| Student A | Central control plane and AI | `src/aiops/central/**`, `web/**`, agent prompts |
| Student B | Edge platform and ML | `src/aiops/edge/**`, `deploy/**`, `experiments/**` |
| Joint | Both | `contracts/**`, `src/aiops/contracts/**`, `src/aiops/common/**`, `tests/security/**`, integration/e2e, thesis results |
| Coding agent | Works under the human who started the session | The task it was given; never merges its own PR |
| Supervisor | Prof. Badiâa Dellal-Hedjazi | Checkpoint reviews (see §8) |

The human who starts an agent session is accountable for what it produces and reviews every diff.

## 2. Branching, commits, PRs

- `main` is the demo/release branch and is always green; `dev` is the integration branch. Both are protected: a PR is required, the `python` and `gitleaks` checks must pass, and only squash merges are allowed.
- Short-lived branches come from `dev` and target `dev`: `feat/S3-B2-outbox`, `fix/S5-A2-revoked-cert`, `docs/S1-J1-readme`. At each sprint demo/checkpoint, open a `dev` → `main` PR so `main` matches what was demonstrated. Never push directly to `main` or `dev`.
- One task = one branch = one PR, ideally < 400 changed lines. Split larger work.
- Conventional Commits with task ID: `feat(edge): transactional outbox [S3-B2]`. Types: feat, fix, test, docs, refactor, chore, ci.
- PR needs: linked task ID, acceptance criteria checklist, "How I verified" (commands + results), "Not verified / known gaps", contract/ADR impact, security impact (yes/no).
- Review: the *other* student reviews anything under Joint ownership or `tests/security`; the owner reviews the rest; the other student skims every PR weekly. Squash merge.
- Never force-push `main`. Never commit `.env`, keys, kubeconfigs, datasets > 50 MB (use `experiments/runs` manifests + external storage).

## 3. The agent session protocol

Start every session with this prompt (adapt the task ID):

```text
Read CLAUDE.md. Then read docs/PRD.md, docs/SPEC.md, docs/AUTONOMY_MATRIX.md and the sprint section in docs/BACKLOG.md.
Task: <TASK-ID>. Restate the acceptance criteria and list the files you will touch, then wait for my OK.
After my OK: write tests first, implement the smallest change, run `make check`, update docs/contracts, and prepare the PR description (verified / not verified).
Stop and ask if you hit a security boundary, a schema change, an ADR-worthy decision, or conflicting requirements.
```

Rules for agents:
- Plan → confirm → test → implement → check → document → PR. No skipping.
- Commit small, frequently. Do not leave the tree broken at the end of a session.
- If you cannot verify something (needs the lab, a cloud key, a Chaos injection), say so explicitly in the PR rather than guessing.
- Parallel agents: one working tree each (`git worktree add ../aiops-<task> -b feat/<task>`), disjoint directories, never the same task. Rebase on `main` before opening the PR.
- Context hygiene: use `/clear` between unrelated tasks; keep `CLAUDE.md` short; link to docs instead of pasting them.

## 4. Definition of Ready (a task may start)
Acceptance criteria written; owner and reviewer named; contracts it depends on exist; test approach known; estimated ≤ 3 working days.

## 5. Definition of Done (a task may close)
- Acceptance criteria demonstrated (command output, test, screenshot, or recorded run).
- Tests: unit + contract; security tests if a boundary is touched; ML work records data source, split, schema/model version, and evaluates on unseen runs; AI work has typed read-only tools, evidence saved, no fabricated result on timeout; remediation work validates target UID, action, policy and approval, is idempotent, and verifies independently.
- `make check` green; CI green.
- No secrets in logs/repo; server-side authorization present.
- Docs, contracts, examples and BACKLOG status updated.
- Works from the documented deployment (compose/Helm/lab), not only a dev workstation.

## 6. Contract change process
1. Open an issue "contract: <schema> vN→vN+1" with motivation and examples.
2. Additive optional fields: allowed within a version. Anything else: new version file (`*.v2.schema.json`) and a transition plan.
3. Update in the same PR: schema, `contracts/examples`, Pydantic model, tests, SPEC/ARCHITECTURE if they mention it.
4. The other student must approve. Run `make schemas`.

## 7. ADR process
Any deviation from SPEC/PRD or new component, dependency class or protocol gets a one-page ADR from `docs/adr/0000-template.md`. Status Proposed → Accepted after the other student agrees. Never edit an accepted ADR's decision; supersede it.

## 8. Cadence (two-week sprints)
| When | What |
|---|---|
| Day 1 | Sprint planning: pick tasks from `BACKLOG.md`, check Definition of Ready, assign owners |
| Mid-sprint | 20-minute sync: blockers, contract needs |
| Last Thursday | Integration: merge to `main`, run e2e/smoke on the lab |
| Last Friday | Demo (recorded, 3-5 min) + retro (what to change next sprint); update `BACKLOG.md` and risks |
| Every 4 sprints | Supervisor checkpoint: demo, results so far, risks, scope decisions |
Checkpoints: after S3 (vertical slice), S6 (UI + identity), S9 (full lifecycle), S11 (freeze evaluation criteria).

## 9. Research hygiene (continuous)
- Every fault run writes `meta.json` via the harness; no unlabeled data.
- Healthy-data soak runs continuously from S2; note any maintenance windows.
- Keep a lab notebook: `experiments/NOTES.md` (dated entries: what changed, why, observations).
- Freeze acceptance criteria and targets (commit hash recorded) before the final evaluation in S11.

## 10. Customer discovery (parallel track, ≤ 2 h/week)
Script in `docs/discovery/interview-script.md`. Target 8-10 interviews and ≥ 3 incident walkthroughs; log in `docs/discovery/` (create on first interview; no confidential customer data in the repo, only anonymized notes). Apply the kill/pivot rule after 5 interviews.

## 11. Security and data handling
- Secrets: `.env` (git-ignored) locally, Kubernetes Secrets in lab; `.env.example` lists names only.
- LLM calls: redact tokens/credentials/hostnames as configured; log prompt/model/tool versions, not secrets.
- Anything from customers needs written permission before use as data.
- Pre-commit runs secret scanning (gitleaks) and ruff.

## 12. Risk and status hygiene
`docs/BACKLOG.md` is the single status board (task rows have status: todo, doing, review, done, cut). Update on every merge. If a sprint slips by more than a third, cut scope by moving tasks down the tiers (record it in an ADR or the retro), not by lowering Definition of Done.
