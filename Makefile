.PHONY: install infra build migrate up down checks check test integration e2e test-all benchmark

COMPOSE_CHECKS = docker compose -f compose.yaml -f compose.test.yaml
RUN_CHECKS = $(COMPOSE_CHECKS) run --rm --no-deps checks

install:
	uv sync --frozen

infra:
	docker compose up -d postgres rabbitmq

migrate:
	docker compose run --rm api alembic upgrade head

build:
	docker compose build api

up: infra build
	$(MAKE) migrate
	docker compose --profile demo up -d --wait api consumer webhook-receiver

down:
	docker compose --profile demo down

checks: build
	$(COMPOSE_CHECKS) build checks

check: checks
	$(RUN_CHECKS) ruff check src tests scripts docker migrations
	$(RUN_CHECKS) ruff format --check src tests scripts docker migrations
	$(RUN_CHECKS) mypy src

test: checks
	$(RUN_CHECKS) pytest tests/unit tests/api --junitxml=work/test-results/unit.xml

integration: checks
	$(RUN_CHECKS) pytest tests/integration --junitxml=work/test-results/integration.xml

e2e: checks
	$(RUN_CHECKS) pytest tests/e2e --junitxml=work/test-results/e2e.xml

test-all: up checks
	$(RUN_CHECKS) pytest tests --junitxml=work/test-results/all.xml

benchmark: checks
	$(RUN_CHECKS) sh -c 'API_KEY="$$E2E_API_KEY" python scripts/benchmark_api.py --url "$$E2E_API_URL"'
