# 06 — Compliance Gate

The single choke point. No presentment and no message reaches an adapter without
passing `compliance.evaluate(action, context)`.

---

## ⚠️ VERIFY BEFORE THE DEMO — read this first

The numeric constants below are **placeholders in config, not asserted facts.**
NPCI and RBI have revised these repeatedly. Before you demo, look up current
figures and fill in the `value` and `source` fields in `config/policy.yaml`:

| Constant | What to verify | Where to look |
|---|---|---|
| `max_presentations_per_cycle` | Permitted re-presentation attempts per NACH debit cycle | NPCI NACH procedural guidelines / circulars |
| `upi_autopay_retry_limits` | Retry constraints specific to UPI Autopay mandates | NPCI UPI Autopay circulars |
| `pre_debit_notice_hours` | Mandatory advance-notice period before a recurring debit | RBI recurring-payments framework |
| `afa_exemption_ceiling_paise` | Value ceiling below which additional factor authentication is not required for recurring transactions | RBI e-mandate circulars |
| `mandate_amount_cap_behaviour` | Whether a charge above the mandate cap can be partially presented | NPCI / RBI mandate rules |
| `quiet_hours_ist` | Permitted contact hours for commercial communication | TRAI UCC / TCCCPR regulations |
| `consent_and_optout` | DND / opt-out obligations on commercial messaging | TRAI TCCCPR; DPDP Act for personal data |

**Do not state a regulatory number on stage you have not checked this week.** In
front of Razorpay judges, a wrong constant on a compliance feature is worse than
not having the feature. If you cannot verify one in time, mark it
`source: UNVERIFIED` in config and say so in the demo — that reads as rigour, not
weakness.

Ask me to pull the current circulars and I will.

---

## `config/policy.yaml` — the constants block

```yaml
constants:
  max_presentations_per_cycle:
    value: 3            # PLACEHOLDER
    source: UNVERIFIED
  min_cooling_off_days:
    value: 2
    source: PRODUCT_CHOICE
  pre_debit_notice_hours:
    value: 24           # PLACEHOLDER
    source: UNVERIFIED
  reserve_days_before_cycle_end:
    value: 1
    source: PRODUCT_CHOICE
  max_contacts_per_week:
    value: 3
    source: PRODUCT_CHOICE
  max_contacts_per_cycle:
    value: 4
    source: PRODUCT_CHOICE
  quiet_hours_ist: {start: "21:00", end: "09:00", source: UNVERIFIED}
  max_consecutive_failed_cycles:
    value: 2
    source: PRODUCT_CHOICE
  payment_link_expiry_days:
    value: 5
    source: PRODUCT_CHOICE
```

Every constant carries a `source`. The dashboard renders them with the source
visible. A judge asking "where does 3 come from" gets an honest answer either
way.

---

## The checks

Each is a class implementing `check(action, ctx) -> Pass | Block(code, message)`.
**All checks run** — no short-circuit — so the ledger records every reason.

### Applies to presentment actions

| Code | Check |
|---|---|
| `MANDATE_NOT_ACTIVE` | `mandate.status == ACTIVE` at execution time, re-read from DB, not from the cached decision snapshot |
| `MANDATE_NOT_IN_VALIDITY` | `valid_from <= now <= valid_until` |
| `AMOUNT_EXCEEDS_MANDATE_CAP` | `amount <= mandate.max_amount_paise` |
| `PRESENTATION_CAP_EXCEEDED` | `cycle.presentations_used < max_presentations_per_cycle` |
| `COOLING_OFF_NOT_ELAPSED` | `now - last_attempt >= min_cooling_off_days` |
| `FREQUENCY_VIOLATION` | no prior successful debit in this mandate's current period |
| `PRE_DEBIT_NOTICE_MISSING` | a `PRE_DEBIT_NOTICE` message exists for this cycle and was sent at least `pre_debit_notice_hours` ago |
| `CYCLE_CLOSED` | `now <= cycle.period_end - reserve_days` |
| `CYCLE_ALREADY_RECOVERED` | `cycle.state != RECOVERED` |
| `DISPUTE_FREEZE` | no open dispute or chargeback on this cycle |
| `TERMINAL_DISPOSITION` | classification disposition is not `TERMINAL` |
| `ACTION_FORBIDDEN_FOR_CAUSE` | action is in the permitted set for this root cause (`04`) |

### Applies to messaging actions

| Code | Check |
|---|---|
| `CUSTOMER_OPTED_OUT` | `customers.opted_out_at IS NULL` |
| `QUIET_HOURS` | current IST time outside the quiet window |
| `WEEKLY_CONTACT_CAP` | contacts to this customer in the trailing 7 simulated days `< max_contacts_per_week` |
| `CYCLE_CONTACT_CAP` | contacts for this cycle `< max_contacts_per_cycle` |
| `TEMPLATE_NOT_APPROVED` | `template_key` is in the approved allowlist |
| `TEMPLATE_VARIABLES_INVALID` | every required variable present, no unfilled placeholders, rendered length within channel limit |
| `NO_CONTACT_FOR_RISK_CASE` | root cause is not `RISK_BLOCK` |
| `DUPLICATE_MESSAGE` | no identical `(cycle, template_key)` message already sent |

### Applies to payment links

| Code | Check |
|---|---|
| `LINK_ALREADY_OPEN` | no unexpired unpaid link exists for this cycle |
| `AMOUNT_MISMATCH` | link amount equals the outstanding cycle amount exactly |
| `CYCLE_ALREADY_RECOVERED` | as above |

### Global kill switches

| Code | Check |
|---|---|
| `MERCHANT_PAUSED` | merchant has not paused automation |
| `RUN_BUDGET_EXCEEDED` | run-level caps on total presentments and total messages not exceeded — a circuit breaker against a logic bug spamming the whole book |
| `CUSTOMER_MANUALLY_HELD` | support has placed a hold on this customer |

`RUN_BUDGET_EXCEEDED` is worth building for its own sake. Being able to say *"if
the agent's logic breaks, the blast radius is bounded at the run level"* is a
sentence that lands with anyone who has operated payments.

---

## Contract

```python
@dataclass(frozen=True)
class Block:
    check: str
    code: str
    message: str          # plain English, judge-readable

@dataclass(frozen=True)
class GateDecision:
    result: GateResult
    blocks: list[Block]
    checks_run: list[str]
    evaluated_at: datetime

def evaluate(action: ProposedAction, ctx: Context) -> GateDecision: ...
```

Rules:

1. `blocks` non-empty implies `result == BLOCKED`. Assert it.
2. The gate **never** raises for a policy violation. A block is a normal return.
   Exceptions are reserved for genuine faults like a DB outage.
3. Every call writes a ledger row: `DECISION` if allowed, `GATE_BLOCKED` if not.
4. The gate is re-evaluated **at execution time**, not only at decision time. The
   world moves between scheduling and firing — the mandate may have been revoked
   yesterday. This re-check is the difference between a demo and a system.

---

## Test suite — build this before the happy path

`tests/test_compliance.py`. One test per check, both directions.

```
test_presentment_blocked_when_mandate_revoked
test_presentment_blocked_when_cap_reached
test_presentment_blocked_when_cooling_off_not_elapsed
test_presentment_blocked_without_pre_debit_notice
test_presentment_blocked_when_amount_over_mandate_cap
test_presentment_blocked_after_cycle_end
test_presentment_blocked_on_terminal_disposition
test_message_blocked_in_quiet_hours
test_message_blocked_when_opted_out
test_message_blocked_at_weekly_cap
test_message_blocked_for_risk_block_cause
test_message_blocked_on_unapproved_template
test_link_blocked_when_open_link_exists
test_all_blocks_returned_not_just_first
test_gate_reevaluated_at_execution_time_after_state_change
test_blocked_action_writes_ledger_row
test_gate_never_raises_on_policy_violation
```

Then the property test that matters most:

```python
def test_no_action_ever_bypasses_gate():
    """Every adapter call in the codebase must be preceded by a gate pass."""
```

Implement it by making adapters accept a `GateToken` that only
`compliance.evaluate()` can mint, and typing the adapter signatures to require
it. Then bypassing the gate is not a discipline problem, it is a compile-time
impossibility. This is a five-minute change that makes a very strong claim
structurally true, and it is exactly the kind of detail that separates first
place from fourth.

---

## Rendering it for judges

The dashboard's compliance panel shows, for the whole run:

- Checks executed: total count
- Actions blocked: count, grouped by code
- **Violations: 0** — where a violation is defined as an executed action that
  would have failed the gate, detected by an independent post-hoc audit pass over
  the ledger

That last one matters. Do not just report "the gate blocked things." Run a
**separate auditor** over the finished ledger that re-derives whether every
executed action was legal, using its own code path. Zero violations found by an
independent auditor is a much stronger claim than zero violations reported by the
thing doing the enforcing.
