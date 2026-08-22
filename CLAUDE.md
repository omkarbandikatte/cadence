# CLAUDE.md — Standing instructions for this repo

Project codename: **Cadence** — an AI agent that recovers failed recurring debits
(UPI Autopay / e-NACH mandates) by predicting *when* the customer's account will
be funded, verifying every action against a compliance gate, and escalating
through bounded channels.

Built for the Razorpay Buildathon, Track 03 (AI Revenue Recovery).

---

## Read these before writing any code

Read in this order. Do not start coding until you have read 02, 03, and 06.

| File | What it locks down |
|---|---|
| `01-PRD.md` | Scope. What is in, what is explicitly out. |
| `02-ARCHITECTURE.md` | Components, the six-stage loop, the simulation clock. |
| `03-DATA-MODEL.md` | Every table and enum. This is the contract. |
| `04-FAILURE-TAXONOMY.md` | Failure code -> root cause -> permitted intervention. |
| `05-DECISION-ENGINE.md` | The timing model and the policy table. |
| `06-COMPLIANCE-GATE.md` | Hard rules. Nothing bypasses these. |
| `07-SYNTHETIC-DATA.md` | The generator. The whole result rests on this. |
| `08-API-CONTRACT.md` | Endpoints and payload shapes. |
| `09-DASHBOARD.md` | The UI spec. |
| `10-EVALUATION.md` | Baseline vs agent, and the metrics we report. |
| `11-BUILD-PLAN.md` | Milestones and the cut order. |

---

## Non-negotiable rules

1. **The compliance gate is not advisory.** No code path may present a debit or
   send a message without passing through `compliance.evaluate()`. A blocked
   action is a valid, logged outcome — never an exception to swallow.

2. **Every decision is explainable.** Any row in `decisions` must carry the
   inputs, the rule or score that fired, and a plain-English `rationale` string
   a judge can read aloud. If you cannot explain it in one sentence, the model
   is too complex for this project.

3. **The ledger is append-only.** No UPDATE, no DELETE on `ledger`. Corrections
   are new rows with `corrects_ledger_id` set.

4. **No real money, ever.** Razorpay test mode keys only. The debit outcome in
   the eval harness comes from the simulator, not from a live gateway.

5. **Deterministic by default.** Every run takes a `seed`. The same seed and the
   same config must reproduce identical results. Judges will re-run this.

6. **Baseline and agent share the same simulator.** They must be indistinguishable
   from the simulator's point of view. If the agent gets a friendlier world than
   the baseline, the headline number is worthless.

7. **No hardcoded regulatory constants.** Presentation caps, notice periods and
   cooling-off windows live in `config/policy.yaml` with a `source` field. See
   the VERIFY block in `06-COMPLIANCE-GATE.md`.

---

## Stack

- Python 3.11, FastAPI, Pydantic v2
- PostgreSQL 15, SQLAlchemy 2.0, Alembic
- APScheduler for the tick loop (not Celery — no broker to babysit)
- `razorpay` Python SDK, **test mode only**
- Next.js 14 (App Router), TypeScript, Tailwind, shadcn/ui, Recharts
- pytest, `pytest-cov`
- No LLM in the hot path. See "Where the LLM goes" below.

## Where the LLM goes

The decision loop is deterministic. An LLM sits in exactly three places:

1. **Rationale writer** — turns a structured decision record into the one-line
   human explanation. Cached, non-blocking, never changes the decision.
2. **Message composer** — drafts the WhatsApp/SMS body from an approved template
   plus variables. Output is validated against the template allowlist before send.
3. **Merchant Q&A** — a read-only natural-language interface over the ledger
   ("why did we not retry mandate M-0142?"). Reads, never writes.

If you find yourself wanting the LLM to *choose* an action, stop. That belongs
in the policy table where it can be tested.

## Layout

```
cadence/
  api/            FastAPI app, routers, dependency wiring
  core/
    ingest/       webhook receiver + normaliser
    classify/     failure code -> root cause
    predict/      funding-window model
    policy/       cause -> intervention decision table
    compliance/   the gate
    execute/      presentment, messaging, payment links
    ledger/       append-only audit writer
  sim/
    clock.py      virtual time
    generator.py  synthetic corpus builder
    bank.py       the debit outcome simulator
  eval/
    runners.py    baseline runner, agent runner
    metrics.py    scoring
  models/         SQLAlchemy models
  config/         policy.yaml, taxonomy.yaml, .env.example
  tests/
web/              Next.js dashboard
docs/             these documents
```

## Conventions

- Money is **paise**, stored as `BIGINT`. Never float. Format at the edge only.
- All timestamps are UTC in the DB. Render IST in the UI. The policy engine
  reasons in IST for anything involving quiet hours or day-of-month.
- IDs are prefixed ULIDs: `mnd_`, `cus_`, `att_`, `dec_`, `led_`, `run_`.
- Enums live in `models/enums.py` and are mirrored in `config/taxonomy.yaml`.
  If they drift, the taxonomy file wins and the tests must fail loudly.
- Never call `datetime.now()` in `core/`. Inject `Clock`. This is what makes the
  30-day demo run in 20 seconds.

## Definition of done for any milestone

- Tests pass, including the compliance test suite.
- A fresh `make demo` from an empty DB reproduces the headline numbers.
- Every new action type writes to the ledger.
