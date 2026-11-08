# central/db: SQLAlchemy models, Alembic migrations, tenant-aware repositories. Never edit an applied migration.

- `base.py` — declarative base with the constraint naming convention (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`).
- `models.py` — every central table; every tenant-owned table carries a non-null `tenant_id`.
- `migrations/` — Alembic environment and versions. `alembic.ini` holds no URL: `env.py` reads `DATABASE_URL`.

The URL never goes in `alembic.ini` because it contains the PostgreSQL password.

## Tables

| Table | Purpose | Key invariants |
|---|---|---|
| `tenants`, `sites`, `users` | identity and topology (S1-A2) | `uq_sites_tenant_name`, `uq_users_tenant_email` |
| `events` | one row per observation forwarded by a site | `uq_events_site_id_event_id` (replay is a no-op); CHECK on `severity` |
| `incidents` | central incident, correlated from site incidents | CHECK on `status`/`severity`; `resolved_at >= opened_at` |
| `incident_links` | site-local incident → central incident | unique `(site_id, local_incident_id)`; cascade from the incident |
| `incident_state_history` | append-only transition log | CHECK on `from_status`/`to_status`; cascade from the incident |
| `audit_events` | sensitive actions (login, approval, policy edit) | tenant + time index |

`events.payload`, `events.entity_ref` and `audit_events.details` are JSONB. The
database does not validate their shape; ingestion validates against
`contracts/schemas/*.json` before insert.

**Known gap:** `incident_state_history` and `audit_events` are append-only by
application convention only. A PostgreSQL trigger that rejects `UPDATE`/`DELETE`
and a restricted role are deferred to the audit hardening work; record it in the
PR that adds them.

## Commands

```bash
make migrate                  # alembic upgrade head, inside the compose network
make migration m="add x"      # autogenerate a revision into migrations/versions
```

PostgreSQL is not published to the host, so migrations run through compose rather
than from a shell. `alembic` is also available directly for inspection
(`uv run alembic history`, `uv run alembic current`) — those do not need a
connection. Offline SQL generation compiles a revision without a server:

```bash
uv run alembic -x db_url='postgresql+psycopg://user:pass@localhost/db' upgrade 0001:0002 --sql
```

## Tests

- `tests/unit/test_models.py` asserts the metadata the migration must mirror
  (unique keys, CHECK values, FK actions, indexes) without a database.
- `tests/integration/test_migrations.py` upgrades and downgrades a real
  PostgreSQL and checks the constraints behave (duplicate event rejected,
  cascade on incident delete, invalid enum rejected). It is skipped unless
  `AIOPS_TEST_DATABASE_URL` points at a throwaway database:

```bash
docker run -d --rm --name aiops-mig-test \
  -e POSTGRES_USER=aiops -e POSTGRES_PASSWORD=throwaway -e POSTGRES_DB=aiops_test \
  -p 127.0.0.1:55432:5432 postgres:16.4-bookworm

AIOPS_TEST_DATABASE_URL='postgresql+psycopg://aiops:throwaway@127.0.0.1:55432/aiops_test' \
  uv run pytest tests/integration/test_migrations.py -q

docker rm -f aiops-mig-test
```

## Rules

- Expand-and-contract: add nullable columns first, backfill, then tighten in a
  later migration. Never edit a migration that has been applied anywhere.
- Keep CHECK constraints instead of PostgreSQL ENUM types so new values are a
  normal migration.
- Repository functions take `tenant_id` as a required argument (S2-A2); no
  query builds its own tenant filter.
