# Contracts v1: freeze record and rules

These schemas are the source of truth for everything that crosses a process or
machine boundary. On a conflict between prose and a schema, the schema wins
(`docs/SPEC.md`), and the conflict is fixed by an ADR or a contract change.

## Status

| Item | Value |
|---|---|
| Version | v1 |
| State | **Freeze candidate** — technical review complete, Student B sign-off pending |
| Review date | 2026-11-05 |
| Freeze tag | `contracts-v1-freeze`, created on the merge commit of the freeze PR |
| Change process | `docs/WORKFLOW.md` §6 |

Freezing means the v1 files below stop changing except for additive optional
fields. Anything else needs a new version file and a transition plan.

## Frozen files

- `schemas/event-envelope.v1.schema.json`
- `schemas/incident.v1.schema.json`
- `schemas/command-envelope.v1.schema.json`
- `schemas/rca-report.v1.schema.json`
- `schemas/run-meta.v1.schema.json`
- `actions/actions.yaml`
- `policies/autonomy.yaml`
- `policies/policy.sample.yaml`

The Pydantic mirrors live in `src/aiops/contracts/` (`events.py`, `incidents.py`,
`commands.py`, `rca.py`, `run_meta.py`, `actions.py`). Example payloads live in
`examples/`; deliberately invalid payloads live in
`tests/fixtures/contracts/invalid/` and are expected to fail validation.

## Rules

1. **Identity is not payload.** `tenant_id` and `site_id` are derived from the
   authenticated identity (mTLS certificate or session), never trusted from an
   edge or agent payload. The command envelope carries `site_id` only so the
   site can compare it with its certificate; a mismatch is rejected.
2. **Timestamps are UTC RFC 3339 and kept separate.** `occurred_at`,
   `observed_at`, `received_at` and `processed_at` are distinct concepts.
   `received_at` and `processed_at` are assigned by central and are not part of
   the edge event payload.
3. **Idempotency keys are explicit.** Events: `(site_id, event_id)`. Incident
   updates: `(site_id, local_incident_id, version)`. Commands: `command_id`
   plus a local execution record. Delivery is at-least-once.
4. **Boundary objects are closed.** `additionalProperties: false` on every
   object that crosses a trust boundary. Two nested maps stay open by design,
   because their shape depends on the event type or action:
   `event.data.payload`, `command.payload.parameters` and
   `command.payload.arguments`. Each producer validates the fields it needs.
5. **Only catalogue actions exist.** Remediation payloads carry an `action_id`
   from `actions/actions.yaml` (`ACT-001`, `ACT-002`, `ACT-003`) and typed
   parameters. There is no shell, kubectl passthrough, free-form patch or
   secret field. `ACT-002` requires `replicas`; `ACT-001`/`ACT-003` take none;
   `ACT-003` always requires approval.
6. **Diagnostics are read-only and named.** The tool enum is closed; adding a
   tool is a contract change. `search_runbooks` is P1.
7. **Evidence beats prose.** RCA facts and root-cause candidates must cite at
   least one evidence id. An unsupported claim belongs in `hypotheses`, and
   `inconclusive` is a valid result.
8. **Runs stay honest.** `run-meta` with `valid: false` must carry a reason;
   `valid: true` must not. Invalid runs stay in the dataset.

## Pre-freeze review changes (2026-11-05)

These changes were made **before** the freeze; no released data exists yet, so
no v2 file is needed:

- Event type enum is now mirrored by a `Literal` in the Pydantic model.
- Incident `entity_refs.kind` now uses the same closed entity enum as events.
- Command diagnostic tools now cover all 12 tools from SPEC §7 (three were
  missing: `get_dependency_graph`, `search_runbooks`, `get_related_incidents`).
- Command validation now enforces ACT-002 `replicas`, empty parameters for
  ACT-001/ACT-003, and a non-null approval for ACT-003.
- RCA root-cause candidates now require at least one evidence id.
- Run metadata enforces the `valid` / `invalid_reason` relationship.
- Added examples for an L1 remediation, an inconclusive RCA and an invalid run.
- Added invalid fixtures so the schemas are tested for rejection, not only
  acceptance.

## Validate

```bash
make schemas                      # schemas parse and every example validates
uv run pytest tests/unit/test_contracts.py -q
make check                        # lint, types, schemas, tests
```

The test suite also checks that every example round-trips through its Pydantic
model and that every fixture in `tests/fixtures/contracts/invalid/` is rejected
by both the JSON Schema and the model.

## Changing a contract

1. Open `contract: <schema> vN -> vN+1` with the motivation and an example.
2. Additive optional fields may stay in vN. Anything else creates a new
   `*.vN+1.schema.json` and a transition plan.
3. In the same PR: schema, examples, Pydantic model, tests, SPEC/architecture
   text, and the BACKLOG status.
4. The other student approves. `make schemas` and `make check` must be green.
5. Never edit a frozen schema in place to make old data fit; add a version and
   a migration/transition instead.

## Sign-off

| Student | Handle | Date | Signature |
|---|---|---|---|
| A (central + AI) | `@LebgaaAbderrahmane` | 2026-11-05 | Reviewed the schemas, models, examples and negative fixtures |
| B (edge + ML) | **pending** | | **Required before the freeze tag** |

The freeze tag is created only after both rows are complete.
