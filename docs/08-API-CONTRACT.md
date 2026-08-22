# 08 — API Contract

FastAPI. All responses `application/json`. Money in paise as integers; the UI
formats. Errors follow RFC 7807-ish: `{"type","title","detail","status"}`.

## Ingest

### `POST /webhooks/razorpay`
Razorpay webhook receiver. Verifies `X-Razorpay-Signature` against the webhook
secret. Idempotent on the event id.

Handles: `payment.failed`, `subscription.charged`, `subscription.pending`,
`subscription.halted`, `payment_link.paid`.

`200 {"received": true, "failure_event_id": "fev_..." | null}`

Signature failure → `401` and a ledger row. Never process an unverified webhook.

### `POST /ingest/replay`
Batch path used by the eval harness and by the demo's "load corpus" button.

```json
{"corpus_id": "cor_...", "run_id": "run_...", "mode": "AGENT"}
```
`202 {"run_id": "...", "events_queued": 247}`

---

## Simulation control

### `POST /sim/corpus`
```json
{"seed": 42, "n_customers": 300, "days": 90, "preset": "default"}
```
`201 {"corpus_id": "...", "stats": {...}}`

### `POST /sim/run`
```json
{"corpus_id": "cor_...", "mode": "BASELINE" | "AGENT" | "ORACLE", "seed": 42}
```
Runs synchronously to completion under `VirtualClock` (seconds, not minutes).
`201 {"run_id": "...", "metrics": {...}}`

### `POST /sim/tick`
Advance the virtual clock by N days without running to completion. Used by the
live demo so you can narrate one day at a time.
```json
{"run_id": "run_...", "days": 1}
```
`200 {"now": "2026-02-02T00:00:00Z", "events": [...]}`

### `POST /sim/inject`
Fire an adversarial case mid-run on stage.
```json
{"run_id": "run_...", "case": "A2_MANDATE_REVOKED", "mandate_id": "mnd_..."}
```
`200 {"injected": true, "ledger_ids": [...]}`

This endpoint is how you produce the staged refusal live rather than pointing at
a log. Build it.

---

## Read models — dashboard

### `GET /runs`
List runs with headline metrics. `?mode=AGENT&limit=20`

### `GET /runs/{run_id}/metrics`
The full scorecard. Shape defined in `10-EVALUATION.md`.

### `GET /runs/compare?baseline={id}&agent={id}&oracle={id}`
The comparison table, pre-computed server-side so the UI does no arithmetic.

```json
{
  "rows": [
    {"metric": "recovery_rate", "label": "Recovery rate",
     "baseline": 0.31, "agent": 0.52, "oracle": 0.79,
     "unit": "ratio", "higher_is_better": true,
     "delta_abs": 0.21, "delta_rel": 0.677,
     "captured_of_available": 0.4375}
  ],
  "corpus_id": "cor_...", "seed": 42, "held_out_customers": 180
}
```

`captured_of_available` = (agent − baseline) / (oracle − baseline). "We captured
44% of the headroom the baseline left on the table" is a better sentence than a
raw percentage, and it is the one that shows you understand your own result.

### `GET /portfolio`
Merchant home. Aggregates at risk, in recovery, recovered, abandoned.
```json
{"at_risk_paise": 11240000, "recovered_paise": 4180000,
 "in_recovery_count": 63, "awaiting_customer_action": 19,
 "escalated_to_you": 7, "churn_flagged": 4}
```

### `GET /cycles?state=IN_RECOVERY&sort=amount_desc&page=1`
Paginated work list. Each row: customer, amount, cause, next action, next action
time, attempts used of cap.

### `GET /cycles/{cycle_id}`
The timeline view. Everything that happened, in order, with rationale.
```json
{
  "cycle": {...}, "mandate": {...}, "customer": {...},
  "classification": {"root_cause": "BALANCE_SHORTFALL", "confidence": 0.95,
                     "matched_rule": "BAL_001"},
  "prediction": {"curve": [...], "best_day_offset": 5, "basis": "CUSTOMER_HISTORY",
                 "feature_contributions": {"customer_term": 0.61,
                   "population_term": 0.14, "gap_term": 0.19,
                   "issuer_term": 0.0, "proximity_penalty": -0.06}},
  "timeline": [
    {"at": "...", "event_type": "PRESENTMENT_RESULT", "rationale": "...",
     "amount_paise": null, "blocked_by": null}
  ],
  "next_action": {"action_type": "SCHEDULE_PRESENTMENT",
                  "scheduled_for": "...", "cancellable": true}
}
```

### `GET /ledger`
Filterable, paginated, append-only view.
`?run_id=&cycle_id=&customer_id=&event_type=&from=&to=&q=`

### `GET /compliance/report?run_id=`
```json
{
  "checks_run": 4821,
  "actions_blocked": 118,
  "blocked_by_code": {"TERMINAL_DISPOSITION": 54, "PRESENTATION_CAP_EXCEEDED": 22,
                      "QUIET_HOURS": 18, "WEEKLY_CONTACT_CAP": 14,
                      "MANDATE_NOT_ACTIVE": 10},
  "independent_audit": {"violations_found": 0, "rows_audited": 4821,
                        "auditor_version": "1.0"},
  "constants": [{"key": "max_presentations_per_cycle", "value": 3,
                 "source": "UNVERIFIED"}]
}
```

Rendering `source` in the API and the UI keeps you honest about the VERIFY block
in `06`.

---

## Actions — merchant control

### `POST /cycles/{cycle_id}/pause`
### `POST /cycles/{cycle_id}/resume`
### `POST /customers/{customer_id}/opt-out`
Sets `opted_out_at`, cancels all pending messages, writes ledger rows.
### `POST /cycles/{cycle_id}/force-link`
Merchant override: send a payment link now. Still passes the gate.
### `POST /merchant/pause-automation`
Global kill switch. Every pending action cancels. Have this on the dashboard as
a visible button — judges notice a kill switch.

---

## Q&A

### `POST /qa`
```json
{"question": "why did we not retry mandate mnd_0142?", "run_id": "run_..."}
```
```json
{"answer": "The mandate was revoked on 18 January...",
 "citations": [{"ledger_id": 8814, "event_type": "GATE_BLOCKED"}],
 "sql_executed": "SELECT ... FROM ledger WHERE mandate_id = ..."}
```

Implementation: constrain the LLM to a **read-only** connection and a small set
of parameterised query templates rather than free-form SQL. Return the executed
query alongside the answer — showing your work turns a possible "is it
hallucinating" objection into a point in your favour. Always cite ledger ids.

---

## Non-functional

- Every mutating endpoint accepts `Idempotency-Key`.
- Every response carries `X-Run-Id` where applicable.
- `GET /healthz` returns DB connectivity, scheduler liveness, and the loaded
  policy config hash.
- OpenAPI at `/docs`. Judges sometimes open it; make sure the schemas are named
  properly rather than `Body_post_sim_run_sim_run_post`.
