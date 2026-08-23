SHELL := /bin/bash
COMPOSE := docker compose
PY := .venv/bin/python
PYTEST := .venv/bin/pytest
ALEMBIC := .venv/bin/alembic
SEED ?= 42
ENV := set -a && [ -f .env ] && . ./.env; set +a;

.PHONY: up down migrate corpus eval report demo test validate-corpus

up:
	$(COMPOSE) up -d
	@echo "waiting for postgres..."
	@until $(COMPOSE) exec -T postgres pg_isready -U cadence >/dev/null 2>&1; do sleep 1; done
	@echo "postgres is up"

down:
	$(COMPOSE) down

migrate:
	$(ENV) $(ALEMBIC) upgrade head
	$(ENV) bash -c 'DATABASE_URL="$$TEST_DATABASE_URL" $(ALEMBIC) upgrade head'

test:
	$(ENV) $(PYTEST) -v

corpus:
	$(ENV) $(PY) -m cadence.sim.generator --seed $(SEED)

validate-corpus:
	$(ENV) $(PY) -m cadence.sim.validate --seed $(SEED)

classify-report:
	$(ENV) $(PY) -m cadence.sim.classify_report --seed $(SEED)

eval:
	@echo "M6 not yet built — see docs/10-EVALUATION.md" && exit 1
	# $(PY) -m cadence.eval.runners --seed $(SEED)

report:
	@echo "M6 not yet built — see docs/10-EVALUATION.md" && exit 1

demo:
	@echo "M8 not yet built — see docs/13-DEMO-SCRIPT.md" && exit 1

clean:
	$(COMPOSE) down -v
