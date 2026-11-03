# deploy/compose: central stack

FastAPI API + worker + PostgreSQL (+ Caddy as the TLS reverse proxy).

## Prerequisites

- Docker with the Compose plugin.
- A `.env` at the repository root:
  ```bash
  cp .env.example .env
  # then set POSTGRES_PASSWORD, SESSION_SECRET, LLM_* in .env
  ```
  `POSTGRES_PASSWORD` must be URL-safe (hex or base64url) because it is embedded
  in the generated `DATABASE_URL`.

## Run

```bash
make up      # docker compose --env-file .env -f deploy/compose/compose.yaml up -d --build
make down
```

`make up` passes `--env-file .env` explicitly: Compose looks for `.env` next to
`compose.yaml` by default, and this repository keeps it at the root.

## Schema

```bash
make migrate                  # alembic upgrade head, inside the compose network
make migration m="add x"      # autogenerate a revision into src/aiops/central/db/migrations
```

PostgreSQL is not published to the host, so Alembic runs as a one-off container
that already has `DATABASE_URL` pointing at `postgres`. `make migrate` is
idempotent: running it twice is a no-op.

## Verify

```bash
docker compose --env-file .env -f deploy/compose/compose.yaml ps
curl -k https://localhost/health/live
curl -k https://localhost/health/ready
curl -k https://localhost/health/dependencies
```

Expected: `postgres` and `api` are `healthy`, `worker` and `proxy` are `running`.
The worker has no HTTP port, so it has no container healthcheck; it logs a
`worker_heartbeat` line every `WORKER_POLL_SECONDS` (default 30 s):

```bash
docker compose --env-file .env -f deploy/compose/compose.yaml logs worker --tail=20
```

## Host names: `localhost` vs `postgres`

`.env` carries `DATABASE_URL` with host `localhost`, because the same value is
used by tooling run on the host (Alembic, tests). Inside containers `localhost`
is the container itself, so `compose.yaml` overrides `DATABASE_URL` with host
`postgres` via the `environment:` block. `environment:` wins over `env_file:`.

If you add another service that talks to PostgreSQL, give it the same override.

## Health endpoints

| Endpoint | Meaning | Status codes |
|---|---|---|
| `GET /health/live` | process is up, no dependency check | always 200 |
| `GET /health/ready` | PostgreSQL answers `SELECT 1` | 200 ready / 503 not ready |
| `GET /health/dependencies` | per-dependency status + latency | always 200 |

Error detail in the payload is redacted and truncated before it reaches logs or
the browser. Migration-head checking is added with the Alembic baseline (S1-A2).

## Troubleshooting

- `POSTGRES_PASSWORD:?set in .env` → `.env` is missing or the variable is empty.
- `api` unhealthy but `postgres` healthy → check `logs api`; the usual cause is a
  `DATABASE_URL` with the wrong host or password.
- Build fails with `Temporary failure in name resolution` while pip installs
  dependencies → containers have no outbound network. On a host running `ufw`,
  the fix is `sudo ufw default allow routed` (inbound stays denied). Verify with
  `docker run --rm alpine nslookup pypi.org`.
- Ports 80/443 already in use → stop whatever serves them (another Caddy, a local
  reverse proxy) before `make up`.
- Caddy uses its internal CA for `localhost`; `curl -k` is expected.
