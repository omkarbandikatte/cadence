SHELL := /bin/bash
COMPOSE := docker compose
PY := .venv/bin/python
PYTEST := .venv/bin/pytest
ALEMBIC := .venv/bin/alembic
SEED ?= 42
ENV := set -a && [ -f .env ] && . ./.env; set +a;

.PHONY: up down clean migrate corpus eval report demo test validate-corpus classify-report fit-predict predict-report run-a1-e2e

up:
	$(COMPOSE) up -d
	@echo "waiting for postgres..."
	@until $(COMPOSE) exec -T postgres pg_isready -U cadence >/dev/null 2>&1; do sleep 1; done
	@echo "postgres is up"

clean:
	$(ENV) bash -c 'psql -h localhost -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "TRUNCATE ledger, pending_actions, decisions, predictions, classifications, failure_events, attempts, messages, payment_links, contact_log, cycles, mandates, customers, issuer_health, funding_calendar, corpus_meta, runs RESTART IDENTITY CASCADE;"'

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

fit-predict:
	$(ENV) $(PY) -m cadence.sim.fit_predict_weights --seed $(SEED)

predict-report:
	$(ENV) $(PY) -m cadence.sim.predict_report --seed $(SEED)

run-a1-e2e:
	$(ENV) $(PY) -m cadence.sim.run_a1_e2e

eval:
	$(ENV) $(PY) -m cadence.eval.run_eval_cli --seed $(SEED)

report:
	$(ENV) $(PY) -m cadence.eval.run_report_cli --seed $(SEED)

demo:
	@echo "M8 not yet built — see docs/13-DEMO-SCRIPT.md" && exit 1
