PYTHON ?= python3.12
UV ?= uv
COMPOSE := docker compose -f deploy/compose/docker-compose.yml
GATEWAY := services/gateway
WEB := services/web

.DEFAULT_GOAL := help

.PHONY: help install dev dev-infra down test lint typecheck eval fmt compose-config ci migrate-samples db-migrate

help:
	@printf '%s\n' \
		'make install        sync Python workspace and npm packages' \
		'make dev            start compose stack (Postgres, RabbitMQ, service stubs)' \
		'make dev-infra      start Postgres and RabbitMQ only' \
		'make down           stop compose stack' \
		'make test           run unit tests' \
		'make lint           ruff, eslint, prettier, mypy, tsc, bandit' \
		'make typecheck      mypy and tsc' \
		'make eval           write docs/RESULTS.md from the eval harness' \
		'make migrate-samples run the pipeline on the three py2 corpus trees' \
		'make db-migrate     apply Alembic migrations to DATABASE_URL' \
		'make fmt            apply ruff and prettier' \
		'make compose-config validate compose YAML' \
		'make ci             lint, typecheck, test, eval'

install:
	$(UV) sync --all-packages --group dev
	npm --prefix $(GATEWAY) ci
	npm --prefix $(WEB) ci

dev:
	$(COMPOSE) up --build

dev-infra:
	$(COMPOSE) up postgres rabbitmq

down:
	$(COMPOSE) down

test:
	$(UV) run pytest
	npm --prefix $(GATEWAY) test
	npm --prefix $(WEB) test

lint: typecheck
	$(UV) run ruff check services/orchestrator/src services/worker/src services/sandbox/src eval/src
	$(UV) run ruff format --check services/orchestrator/src services/worker/src services/sandbox/src eval/src services/orchestrator/tests services/worker/tests services/sandbox/tests eval/tests
	$(UV) run bandit -q -r services/orchestrator/src services/worker/src services/sandbox/src eval/src
	npm --prefix $(GATEWAY) run lint
	npm --prefix $(WEB) run lint
	npm --prefix $(GATEWAY) run format:check
	npm --prefix $(WEB) run format:check

typecheck:
	$(UV) run mypy
	npm --prefix $(GATEWAY) run typecheck
	npm --prefix $(WEB) run typecheck

eval:
	$(UV) run python -m legacylift_eval.run

migrate-samples:
	$(UV) run python -m legacylift_worker.cli migrate corpus/py2_textkit --out reports/py2_textkit --timeout 120
	$(UV) run python -m legacylift_worker.cli migrate corpus/py2_pricing --out reports/py2_pricing --timeout 120
	$(UV) run python -m legacylift_worker.cli migrate corpus/py2_counts --out reports/py2_counts --timeout 120

db-migrate:
	$(UV) run alembic -c services/worker/alembic.ini upgrade head

fmt:
	$(UV) run ruff check --fix services/orchestrator/src services/worker/src services/sandbox/src eval/src
	$(UV) run ruff format services/orchestrator/src services/worker/src services/sandbox/src eval/src services/orchestrator/tests services/worker/tests services/sandbox/tests eval/tests
	npm --prefix $(GATEWAY) run format
	npm --prefix $(WEB) run format

compose-config:
	$(COMPOSE) config --quiet

ci: lint test eval
