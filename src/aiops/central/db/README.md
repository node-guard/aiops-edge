# central/db: SQLAlchemy models, Alembic migrations, tenant-aware repositories. Never edit an applied migration.

- `base.py` — declarative base with the constraint naming convention (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`).
- `models.py` — `tenants`, `sites`, `users`; every tenant-owned table carries a non-null `tenant_id`.
- `migrations/` — Alembic environment and versions. `alembic.ini` holds no URL: `env.py` reads `DATABASE_URL`.

The URL never goes in `alembic.ini` because it contains the PostgreSQL password.

## Commands

```bash
make migrate                  # alembic upgrade head, inside the compose network
make migration m="add x"      # autogenerate a revision into migrations/versions
```

PostgreSQL is not published to the host, so migrations run through compose rather
than from a shell. `alembic` is also available directly for inspection
(`uv run alembic history`, `uv run alembic current`) — those do not need a
connection.

## Rules

- Expand-and-contract: add nullable columns first, backfill, then tighten in a
  later migration. Never edit a migration that has been applied anywhere.
- Keep CHECK constraints instead of PostgreSQL ENUM types so new values are a
  normal migration.
