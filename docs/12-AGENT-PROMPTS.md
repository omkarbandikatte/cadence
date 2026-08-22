# 12 — Coding Agent Prompts

Copy-paste prompts for Claude Code / Cursor, one per milestone. Each is scoped so
the agent can finish and you can verify before moving on.

## Ground rules for driving the agent

1. **Put `CLAUDE.md` at the repo root and `docs/` beside it.** Every prompt below
   assumes the agent can read them.
2. **One milestone per session.** Long sessions drift. When a milestone lands,
   commit, clear context, start fresh.
3. **Ask for tests in the same prompt as the code.** Retrofitting tests onto
   agent-written code is slower than asking once.
4. **Verify the invariant, not the vibe.** Each prompt below ends with a
   verification command. Run it.
5. **When the agent proposes a schema change, stop.** Schema is frozen after
   hour 2. Make it work within `03` or take the change to the whole team.

---

## M0 — Scaffold

```
Read docs/02-ARCHITECTURE.md and docs/03-DATA-MODEL.md.

Scaffold the repo exactly as laid out in CLAUDE.md. Include:
- docker-compose.yml with Postgres 15
- SQLAlchemy 2.0 models for every table in 03, with the enums in models/enums.py
- Alembic initial migration, including the append-only trigger on ledger
- The Clock protocol in sim/clock.py with RealClock and VirtualClock.
  VirtualClock advances in ticks; one tick defaults to one simulated day.
- A Makefile with targets: up, down, migrate, corpus, eval, report, demo, test
- pytest configured, one smoke test that creates and reads each model

Do not implement business logic. Do not call datetime.now() anywhere outside
sim/clock.py.

Verify: `make up && make migrate && make test` passes, and a test proves that
UPDATE on ledger raises.
```

## M1 — Generator (critical path, do this before anything else)

```
Read docs/07-SYNTHETIC-DATA.md in full, then docs/03-DATA-MODEL.md.

Implement sim/generator.py and sim/bank.py.

Requirements:
- Four customer segments with the funding processes described, including the
  post-credit spend spike. The spike is essential: it must create a 2-4 day
  optimal retry window, not a "wait longer always wins" world.
- Weekend/holiday shifting on credit dates.
- Correlated issuer outage windows that hit every mandate on that issuer at once.
- observed_success_rate per issuer per day, computed from attempts plus
  background synthetic traffic.
- Cause mix per the table in 07.
- All 12 adversarial cases planted and tagged in corpus_meta.
- Train/held-out split BY CUSTOMER, 40/60.
- Every random draw from an explicit numpy Generator seeded from one root seed.
  No global random state.

sim/bank.py resolves a presentment against the funding calendar and outage
windows. It must never be importable from core/.

Also implement the four validation checks V1-V4 from 07 as
`make validate-corpus`.

Verify: `make corpus SEED=42` twice produces identical output. `make
validate-corpus` reports an oracle ceiling between 0.75 and 0.85, a
fixed-interval baseline clearly below it, and a visible day-of-month peak for
salaried segments. If the ceiling is outside that band, tune the spend
parameters and tell me what you changed.
```

## M2 — Ingest and classifier

```
Read docs/04-FAILURE-TAXONOMY.md and docs/08-API-CONTRACT.md.

Implement core/ingest and core/classify.

- POST /webhooks/razorpay with signature verification, idempotent on event id
- POST /ingest/replay for batch corpus replay
- Normaliser producing FailureEvent
- Classifier: exact code match, then description substring at 0.8x confidence,
  then the issuer corroboration pass in step 3 of 04, then default to
  UNKNOWN/TERMINAL
- Load rules from config/taxonomy.yaml; the file is the source of truth and the
  enums must be validated against it at startup

Tests: one per taxonomy rule, plus unmapped code degrades to UNKNOWN/TERMINAL,
plus the corroboration downgrade and upgrade paths both fire.

Verify: run the classifier over the corpus and print per-cause precision and
recall against ground truth. Report the confusion matrix.
```

## M3 — Compliance gate (build before the happy path)

```
Read docs/06-COMPLIANCE-GATE.md in full.

Implement core/compliance.

- Every check listed, as a separate named class
- All checks run; no short-circuit; blocks accumulate
- evaluate() returns GateDecision and never raises on a policy violation
- Constants load from config/policy.yaml including the `source` field
- Implement the GateToken pattern: adapters in core/execute accept a GateToken
  that only compliance.evaluate() can construct, so bypassing the gate is a type
  error rather than a discipline problem
- Every evaluation writes a ledger row

Write the full test suite listed at the end of 06, including
test_all_blocks_returned_not_just_first and
test_gate_reevaluated_at_execution_time_after_state_change.

Verify: `pytest tests/test_compliance.py -v` all green, and a test proves no
adapter can be called without a GateToken.
```

## M4 — Funding-window model

```
Read docs/05-DECISION-ENGINE.md Part A.

Implement core/predict.

- All five terms: customer, population, gap, issuer, proximity penalty
- Circular Gaussian smoothing (sigma 1.5) on the day-of-month histogram
- Weekend/holiday shifting
- min_history_successes gate: below it, w_cust = 0 and basis = POPULATION_PRIOR
- gap_term fitted on the TRAIN split only
- Constrained argmax per the constraint list
- Persist the full curve, basis, and per-term contributions to predictions

Then implement a weight grid search over the train split maximising recovered
rupees per presentation consumed. Write the winning weights into policy.yaml.

Verify: report mean_days_from_optimal and hit_rate_within_2_days on the HELD-OUT
split only. Confirm SALARIED_MONTH_END scores comparably to
SALARIED_MONTH_START — if it does not, the customer term is not working and I
need to know.
```

## M5 — Policy, execution, ledger

```
Read docs/05-DECISION-ENGINE.md Part B and docs/02-ARCHITECTURE.md.

Implement core/policy, core/execute, core/ledger, and the scheduler.

- Policy engine reading policy.yaml, returning ordered candidates, re-invoked on
  gate rejection without repeating a rejected candidate
- pending_actions table plus an APScheduler tick loop driven by the injected
  Clock
- All cancellation rules from 05
- All stopping rules from 05
- Adapters with Sim and Live implementations behind one interface
- Ledger row for every state change, in the same transaction

Verify: run one adversarial case end to end (A1) and print the ledger for that
cycle. Every row must have a non-empty rationale.
```

## M6 — Eval harness

```
Read docs/10-EVALUATION.md.

Implement eval/runners.py, eval/metrics.py, eval/auditor.py, and the report
generator.

- Three arms: BASELINE, AGENT, ORACLE, all against the same corpus, seed, bank
  and clock
- A test asserting all three arms issue identical calls to the simulator
  interface
- The baseline must be competent: fixed T+1/T+3/T+5, dunning message per failure,
  stops at the presentation cap. It lacks classification, timing, gate and link
  fallback — nothing else.
- Every metric in 10
- The independent auditor re-derives legality from the ledger WITHOUT importing
  core/compliance. Duplicated logic is intentional here.
- Multi-seed runner: 5 seeds, mean and spread, bootstrap CI on the recovery-rate
  delta
- HTML report with all 8 sections listed in 10

Verify: `make clean && make corpus SEED=42 && make eval SEED=42 && make report`
from an empty DB. Print the three-arm table and the auditor's violation count
for the agent arm, which must be 0.
```

## M7 — Dashboard

```
Read docs/09-DASHBOARD.md in full, and docs/08-API-CONTRACT.md.

Build the Next.js dashboard. Follow the design direction in 09 exactly — the
passbook/mandate-form vernacular, the token values as given, no red anywhere,
tabular monospace for all figures.

Priority order:
1. The month strip component. This is the signature element; build it first and
   make it excellent. Baseline attempts as hollow markers, Cadence's as a filled
   violet stamp, cell height as historical success probability by day-of-month.
2. Run comparison screen with the full-width month strip and the three-arm table
3. Ledger table with the blocked-only toggle and CSV export
4. Cycle timeline with the diagnosis block and per-term contribution bars
5. Portfolio screen

Responsive to 390px. Visible focus rings. prefers-reduced-motion respected. The
only animation in the product is the one-time month strip reveal on the
comparison screen.

Verify: screenshot each screen at 1440px and 390px and show me.
```

## M8 — Live demo controls

```
Implement POST /sim/tick and POST /sim/inject per docs/08-API-CONTRACT.md, and
wire them to a hidden demo control panel in the dashboard (keyboard shortcut, not
a visible button).

/sim/inject must support all 12 adversarial case ids. Case A2
(mandate revoked mid-schedule) needs to be flawless — it is the staged refusal
in the live demo. Injecting it must, within one tick, produce a visible
GATE_BLOCKED ledger row with a human-readable rationale, and the pending
presentment must show as cancelled in the UI.

Verify: from the dashboard, inject A2 and show me the resulting ledger rows.
```

---

## Prompt patterns that work here

**When the agent over-engineers:**
> Stop. Re-read CLAUDE.md. This is a 48-hour hackathon build. Give me the
> simplest thing that satisfies the spec and the tests, with no abstraction that
> is not used twice.

**When a number looks too good:**
> This result looks suspiciously strong. Before we accept it, check for leakage:
> is the model reading any field listed as generator-only in docs/07? Is the
> split by customer or by event? Re-run on held-out only and show me both.

**When you need a second opinion on your own design:**
> Read docs/05 and argue the strongest case that the funding-window model is
> unnecessary — that a simple "retry on day 2 and day 17" heuristic captures most
> of the value. Then tell me whether the corpus supports that argument.

That last one is worth running before the demo. If a two-line heuristic matches
your model, a judge will find it, and you want to be the one who found it first.
