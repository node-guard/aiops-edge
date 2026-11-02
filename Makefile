.PHONY: setup check lint types test test-sec schemas up down lab-up lab-down fmt

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

up:
	docker compose -f deploy/compose/compose.yaml up -d --build

down:
	docker compose -f deploy/compose/compose.yaml down

lab-up:
	bash deploy/lab/lab-up.sh

lab-down:
	bash deploy/lab/lab-down.sh
