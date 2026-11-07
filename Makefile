.PHONY: setup check lint types test test-sec schemas helm-check up down lab-up lab-check lab-down shop-demo-build shop-demo-deploy shop-demo-delete load fmt migrate migration

setup:
	uv sync --all-extras --dev
	uv run pre-commit install || true

lint:
	uv run ruff check src tests experiments deploy
	uv run ruff format --check src tests experiments deploy

types:
	uv run mypy src/aiops/contracts src/aiops/common

schemas:
	uv run python scripts/validate_contracts.py

test:
	uv run pytest tests/unit tests/integration -q

test-sec:
	uv run pytest tests/security -q

check: lint types schemas helm-check test test-sec

# The chart is the edge deployment contract: render it on every check.
# Requires `helm` (https://helm.sh/docs/intro/install/); CI installs it too.
helm-check:
	helm lint --strict deploy/helm/edge-stack
	helm template edge-stack deploy/helm/edge-stack --namespace aiops-system > /dev/null

fmt:
	uv run ruff format src tests experiments deploy

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

# Requires KUBECONFIG pointing at the lab; the guard refuses any other cluster.
shop-demo-build:
	bash deploy/shop-demo/scripts/build-and-load.sh

shop-demo-deploy:
	bash deploy/lab/lib/lab-guard.sh
	kubectl apply -k deploy/shop-demo

shop-demo-delete:
	bash deploy/lab/lib/lab-guard.sh
	kubectl delete -k deploy/shop-demo

# Healthy HTTP load for the soak (S2-B3). Never calls the fault hooks.
load:
	LOAD_PROFILE=$(or $(PROFILE),standard) HOST=$(or $(HOST),http://192.168.100.10:30080) \
		bash experiments/load/run.sh
