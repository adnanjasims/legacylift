PYTHON ?= python3.12
UV ?= uv
VENV_PYTHON := $(CURDIR)/.venv/bin/python
COMPOSE := docker compose -f deploy/compose/docker-compose.yml
GATEWAY := services/gateway
WEB := services/web

.DEFAULT_GOAL := help

JAVA_M2 := $(CURDIR)/reports/m2
export MAVEN_REPO_LOCAL := $(JAVA_M2)
JAVA8_IMAGE := maven:3.9-eclipse-temurin-8
JAVA21_IMAGE := maven:3.9-eclipse-temurin-21
REWRITE_PLUGIN := org.openrewrite.maven:rewrite-maven-plugin:6.46.1
REWRITE_RECIPES := org.openrewrite.recipe:rewrite-migrate-java:3.42.1
REWRITE_RECIPE := org.openrewrite.java.migrate.UpgradeToJava21

.PHONY: help install dev dev-infra down test lint typecheck eval fmt compose-config ci migrate-samples db-migrate e2e java-deps _java-seed _java-seed-rewrite k8s-render kind-up kind-load kind-apply

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
		'make java-deps       seed reports/m2 for offline Maven + OpenRewrite' \
		'make migrate-samples run the pipeline on the py2 and Java 8 corpus trees' \
		'make db-migrate     apply Alembic migrations to DATABASE_URL' \
		'make fmt            apply ruff and prettier' \
		'make compose-config validate compose YAML' \
		'make e2e            Playwright against the web preview server' \
		'make k8s-render     print the kind overlay (kubectl kustomize)' \
		'make kind-up        create the local kind cluster' \
		'make kind-load      build service images and load them into kind' \
		'make kind-apply     apply the kind overlay' \
		'make ci             lint, typecheck, test, eval, e2e'

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
	$(VENV_PYTHON) -m pytest
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
	$(VENV_PYTHON) -m legacylift_eval.run

java-deps:
	mkdir -p "$(JAVA_M2)"
	$(MAKE) _java-seed SAMPLE=corpus/java8_box IMAGE=$(JAVA8_IMAGE)
	$(MAKE) _java-seed SAMPLE=corpus/java8_urlkit IMAGE=$(JAVA8_IMAGE)
	$(MAKE) _java-seed-rewrite SAMPLE=corpus/java8_box
	$(MAKE) _java-seed-rewrite SAMPLE=corpus/java8_urlkit
	docker run --rm -v "$(JAVA_M2):/m2" $(JAVA21_IMAGE) chmod -R a+rX /m2

_java-seed:
	docker run --rm \
		-v "$(JAVA_M2):/m2" \
		-v "$(CURDIR)/$(SAMPLE):/src:ro" \
		-w /tmp \
		$(IMAGE) \
		sh -c 'cp -a /src /tmp/work && cd /tmp/work && mvn -B -Dmaven.repo.local=/m2 test'

_java-seed-rewrite:
	docker run --rm \
		-v "$(JAVA_M2):/m2" \
		-v "$(CURDIR)/$(SAMPLE):/src:ro" \
		-w /tmp \
		$(JAVA21_IMAGE) \
		sh -c 'cp -a /src /tmp/work && cd /tmp/work && mvn -B -Dmaven.repo.local=/m2 \
			$(REWRITE_PLUGIN):run \
			-Drewrite.recipeArtifactCoordinates=$(REWRITE_RECIPES) \
			-Drewrite.activeRecipes=$(REWRITE_RECIPE) \
			-Drewrite.pomCacheEnabled=false'

migrate-samples:
	$(VENV_PYTHON) -m legacylift_worker.cli migrate corpus/py2_textkit --out reports/py2_textkit --timeout 120
	$(VENV_PYTHON) -m legacylift_worker.cli migrate corpus/py2_pricing --out reports/py2_pricing --timeout 120
	$(VENV_PYTHON) -m legacylift_worker.cli migrate corpus/py2_counts --out reports/py2_counts --timeout 120
	$(VENV_PYTHON) -m legacylift_worker.cli migrate corpus/java8_box --out reports/java8_box --timeout 300 --memory-mb 1536
	$(VENV_PYTHON) -m legacylift_worker.cli migrate corpus/java8_urlkit --out reports/java8_urlkit --timeout 300 --memory-mb 1536

db-migrate:
	$(UV) run alembic -c services/worker/alembic.ini upgrade head

fmt:
	$(UV) run ruff check --fix services/orchestrator/src services/worker/src services/sandbox/src eval/src
	$(UV) run ruff format services/orchestrator/src services/worker/src services/sandbox/src eval/src services/orchestrator/tests services/worker/tests services/sandbox/tests eval/tests
	npm --prefix $(GATEWAY) run format
	npm --prefix $(WEB) run format

compose-config:
	$(COMPOSE) config --quiet

e2e:
	npm --prefix $(WEB) run e2e

k8s-render:
	kubectl kustomize deploy/k8s/overlays/kind

kind-up:
	kind create cluster --name legacylift --config deploy/k8s/overlays/kind/cluster.yaml

kind-load:
	docker build -t legacylift-gateway:local services/gateway
	docker build -t legacylift-orchestrator:local services/orchestrator
	docker build -t legacylift-sandbox:local services/sandbox
	docker build -t legacylift-web:local services/web
	docker build -t legacylift-worker:local -f services/worker/Dockerfile .
	kind load docker-image legacylift-gateway:local --name legacylift
	kind load docker-image legacylift-orchestrator:local --name legacylift
	kind load docker-image legacylift-sandbox:local --name legacylift
	kind load docker-image legacylift-web:local --name legacylift
	kind load docker-image legacylift-worker:local --name legacylift

kind-apply:
	kubectl apply -k deploy/k8s/overlays/kind

ci: lint test eval e2e
