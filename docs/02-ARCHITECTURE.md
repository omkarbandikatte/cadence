# 02 — Architecture

## The loop

Every failed debit passes through six stages. Each stage is a pure-ish function
with an explicit input and output record, and each writes to the ledger.

```
  webhook / batch replay
          |
          v
  [1] INGEST ............ normalise to FailureEvent
          |
          v
  [2] CLASSIFY .......... FailureEvent -> RootCause + confidence
          |
          v
  [3] PREDICT ........... customer history + priors -> FundingWindow
          |               (only invoked for balance-shortfall causes)
          v
  [4] POLICY ............ (RootCause, FundingWindow, state) -> ProposedAction
          |
          v
  [5] GATE .............. ProposedAction -> Allowed | Blocked(reason)
          |                        |
          |                        +--> ledger: BLOCKED, stop
          v
  [6] EXECUTE ........... presentment | message | payment link | reauth | stop
          |
          v
      ledger + outcome -> feeds back into [3] as new history
```

**The gate is stage five, not stage two.** Classification and prediction are
allowed to propose anything; the gate is the single choke point. This is
deliberate — it means there is exactly one place to audit, and one place to test.

## Components

### `core/ingest`
Receives `subscription.charged`, `payment.failed`, `subscription.pending` and
`subscription.halted` webhooks, plus a `POST /replay` batch path used by the
eval harness. Normalises everything into a single `FailureEvent`. Verifies
webhook signature. Idempotent on `(mandate_id, cycle_id, attempt_no)`.

### `core/classify`
Deterministic rules first: a lookup from gateway/bank failure code to root cause,
loaded from `config/taxonomy.yaml`. Codes not in the table fall to a secondary
heuristic on the failure description string, and finally to `UNKNOWN` with
confidence 0. `UNKNOWN` is treated as terminal — we do not retry what we do not
understand. Emit `(cause, subtype, confidence, matched_rule)`.

### `core/predict`
The funding-window model. Input: customer's prior successful debit dates, prior
failure→success gaps, merchant category, current date, issuer health series.
Output: a probability-of-success curve over the next 14 days plus the argmax day,
and a `basis` field recording which prior dominated. Full spec in `05`.

### `core/policy`
A decision table, not a model. `(root_cause, attempt_no, cycle_state,
days_to_cycle_end)` maps to an ordered list of candidate actions. Returns the
first candidate; the gate may reject it, in which case policy is re-invoked with
the rejection recorded so it does not propose the same thing twice.

### `core/compliance`
The gate. A list of named `Check` objects, each returning
`Pass | Block(code, message)`. All checks run — we do not short-circuit, because
the ledger should record every reason an action was blocked, not just the first.
Spec in `06`.

### `core/execute`
Adapters. `PresentmentAdapter` (Razorpay Subscriptions test mode, or the
simulator in eval runs), `MessagingAdapter` (WhatsApp Cloud API with SMS
fallback), `PaymentLinkAdapter` (Razorpay Payment Links test mode),
`ReauthAdapter` (new mandate authorisation link). Every adapter is behind an
interface with a `Sim` implementation so the eval harness never touches network.

### `core/ledger`
Append-only writer. One method: `record(event)`. Enforced at the DB level with a
trigger that rejects UPDATE and DELETE on the table.

### `sim/`
The part most teams skip and then regret.

- `clock.py` — `Clock` protocol with `RealClock` and `VirtualClock`. `VirtualClock`
  advances in ticks (default one tick = one simulated day) and is the only source
  of time inside `core/`. This is what lets a 30-day recovery campaign run in the
  20 seconds you have on stage.
- `generator.py` — builds the corpus. Spec in `07`.
- `bank.py` — the outcome oracle. Given a presentment attempt at simulated time
  T against customer C, decides success/failure and the failure code, using the
  *ground truth* funding calendar and issuer outage windows that the generator
  laid down. **`bank.py` must never be importable from `core/`.** Enforce with a
  test that greps imports.

### `eval/`
`runners.py` exposes `run_baseline(corpus, seed)` and `run_agent(corpus, seed)`.
Both drive the same `VirtualClock` over the same corpus against the same `bank`.
`metrics.py` scores both and emits the comparison table.

### `api/` and `web/`
FastAPI serves the dashboard and the Q&A endpoint. Next.js renders. Spec in `08`
and `09`.

## The two execution modes

| | **Live mode** | **Eval mode** |
|---|---|---|
| Clock | `RealClock` | `VirtualClock` |
| Time source | wall clock | tick loop |
| Presentment | Razorpay test API | `sim/bank.py` |
| Messaging | WhatsApp Cloud API | `SimMessaging` (records, does not send) |
| Payment link | Razorpay test API | `SimPaymentLink` with a scripted pay-rate |
| Used for | the live demo slice | the headline numbers |

Both modes run identical `core/` code. The only difference is what gets injected.
Say this explicitly to judges — it is the reason the numbers mean anything.

## Sequence: a balance-shortfall recovery

```
Day 0   Debit presented, fails, code INSUFFICIENT_FUNDS
        -> classify: BALANCE_SHORTFALL, conf 0.95
        -> predict: customer's last 4 successes cleared on the 2nd-4th;
                    today is the 27th; peak funding probability day 5 (the 2nd)
        -> policy: SCHEDULE_RETRY(day 5) + PRE_DEBIT_NOTICE(day 3)
        -> gate: mandate active, within cap, presentation 1 of N, notice
                 lead time satisfiable, customer not opted out, not quiet hours
        -> ledger: DECISION recorded with rationale

Day 3   -> gate re-check (state may have changed)
        -> execute: WhatsApp pre-debit notice, amount + date + top-up prompt
        -> ledger: MESSAGE_SENT

Day 5   -> gate re-check
        -> execute: presentment
        -> bank: customer funded on day 4 -> SUCCESS
        -> ledger: RECOVERED, 149900 paise, 1 retry, 1 message
```

## Sequence: a blocked action

```
Day 0   Debit fails, code MANDATE_REVOKED
        -> classify: MANDATE_DEFECT / REVOKED, conf 1.0
        -> predict: skipped (not a timing problem)
        -> policy: candidate 1 = REQUEST_REAUTH
        -> gate: mandate_active = BLOCK(MANDATE_NOT_ACTIVE)
                 ... but REQUEST_REAUTH does not require an active mandate,
                 so the check set for this action type is different.
        -> gate passes on the reauth-specific check set
        -> execute: send reauth link, mark subscription AWAITING_REAUTH
        -> ledger: DECISION + MESSAGE_SENT, and critically:
                   NO_PRESENTMENT with reason "mandate revoked; presenting
                   would be non-compliant"
```

That last ledger row is the one you point at on stage.

## What we deliberately did not build

- **No message queue.** APScheduler plus a `pending_actions` table with a
  `run_at` column. A hackathon does not need Kafka and a broker is one more
  thing to fail at 4am.
- **No LLM in the decision path.** See `CLAUDE.md`.
- **No microservices.** One FastAPI process, one Postgres, one Next.js app.
