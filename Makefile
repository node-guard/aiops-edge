.PHONY: setup check lint types test test-sec schemas up down lab-up lab-check lab-down fmt migrate migration

setup:
	uv sync --all-extras --dev
	uv run pre-commit install || true

lint:
	uv run ruff check src tests experiments
	uv run ruff format --check src tests experiments

types:
	uv run mypy src/aiops/contracts src/aiops/common

schemas:
	uv run python scripts/validate_contracts.py

test:
	uv run pytest tests/unit tests/integration -q

test-sec:
	uv run pytest tests/security -q

check: lint types schemas test test-sec

fmt:
	uv run ruff format src tests experiments

# `docker compose` looks for `.env` next to compose.yaml; ours is at the repo
# root, so pass it explicitly for interpolation.
COMPOSE := docker compose --env-file .env -f deploy/compose/compose.yaml

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

# Migrations run inside the compose network: PostgreSQL is not published to the
# host, and the container already has DATABASE_URL pointing at `postgres`.
migrate:
	$(COMPOSE) run --rm api alembic upgrade head

# Autogenerate writes into the mounted host directory, so run as the host UID.
migration:
	@test -n "$(m)" || { echo 'usage: make migration m="describe the change"'; exit 1; }
	$(COMPOSE) run --rm --user "$$(id -u):$$(id -g)" \
		-v "$(CURDIR)/src/aiops/central/db/migrations:/app/src/aiops/central/db/migrations" \
		api alembic revision --autogenerate -m "$(m)"

lab-up:
	bash deploy/lab/lab-up.sh

lab-check:
	bash deploy/lab/lab-up.sh --check

lab-down:
	bash deploy/lab/lab-down.sh $(ARGS)
