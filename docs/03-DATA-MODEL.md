# 03 — Data Model

All money in **paise**, `BIGINT`. All timestamps `TIMESTAMPTZ`, stored UTC.
IDs are prefixed ULIDs (`mnd_01H...`).

## Enums

```python
# models/enums.py  — must stay in sync with config/taxonomy.yaml

class RootCause(str, Enum):
    BALANCE_SHORTFALL   = "BALANCE_SHORTFALL"
    ISSUER_DEGRADED     = "ISSUER_DEGRADED"
    MANDATE_DEFECT      = "MANDATE_DEFECT"
    INSTRUMENT_DEFECT   = "INSTRUMENT_DEFECT"
    TECHNICAL_TRANSIENT = "TECHNICAL_TRANSIENT"
    RISK_BLOCK          = "RISK_BLOCK"
    UNKNOWN             = "UNKNOWN"

class CauseSubtype(str, Enum):
    # MANDATE_DEFECT
    REVOKED = "REVOKED"; EXPIRED = "EXPIRED"
    AMOUNT_EXCEEDS_CAP = "AMOUNT_EXCEEDS_CAP"
    FREQUENCY_VIOLATION = "FREQUENCY_VIOLATION"
    NOT_YET_ACTIVE = "NOT_YET_ACTIVE"
    # INSTRUMENT_DEFECT
    CARD_EXPIRED = "CARD_EXPIRED"; ACCOUNT_CLOSED = "ACCOUNT_CLOSED"
    ACCOUNT_FROZEN = "ACCOUNT_FROZEN"; ACCOUNT_DORMANT = "ACCOUNT_DORMANT"
    # ISSUER_DEGRADED
    ISSUER_DOWN = "ISSUER_DOWN"; RAIL_DEGRADED = "RAIL_DEGRADED"
    # other
    NONE = "NONE"

class Disposition(str, Enum):
    RECOVERABLE_TIMING   = "RECOVERABLE_TIMING"    # retry, timing matters
    RECOVERABLE_IMMEDIATE= "RECOVERABLE_IMMEDIATE" # retry now, safe
    RECOVERABLE_ACTION   = "RECOVERABLE_ACTION"    # needs customer action
    TERMINAL             = "TERMINAL"              # do not present again

class ActionType(str, Enum):
    SCHEDULE_PRESENTMENT = "SCHEDULE_PRESENTMENT"
    PRESENT_NOW          = "PRESENT_NOW"
    PRE_DEBIT_NOTICE     = "PRE_DEBIT_NOTICE"
    TOPUP_NUDGE          = "TOPUP_NUDGE"
    SEND_PAYMENT_LINK    = "SEND_PAYMENT_LINK"
    REQUEST_REAUTH       = "REQUEST_REAUTH"
    REQUEST_INSTRUMENT_UPDATE = "REQUEST_INSTRUMENT_UPDATE"
    WAIT_ISSUER_RECOVERY = "WAIT_ISSUER_RECOVERY"
    ESCALATE_TO_MERCHANT = "ESCALATE_TO_MERCHANT"
    STOP_MARK_CHURN      = "STOP_MARK_CHURN"
    NO_ACTION            = "NO_ACTION"

class GateResult(str, Enum):
    ALLOWED = "ALLOWED"; BLOCKED = "BLOCKED"

class LedgerEventType(str, Enum):
    FAILURE_INGESTED = "FAILURE_INGESTED"
    CLASSIFIED       = "CLASSIFIED"
    PREDICTED        = "PREDICTED"
    DECISION         = "DECISION"
    GATE_BLOCKED     = "GATE_BLOCKED"
    PRESENTMENT_SENT = "PRESENTMENT_SENT"
    PRESENTMENT_RESULT = "PRESENTMENT_RESULT"
    MESSAGE_SENT     = "MESSAGE_SENT"
    MESSAGE_SUPPRESSED = "MESSAGE_SUPPRESSED"
    LINK_CREATED     = "LINK_CREATED"
    LINK_PAID        = "LINK_PAID"
    REAUTH_REQUESTED = "REAUTH_REQUESTED"
    RECOVERED        = "RECOVERED"
    ABANDONED        = "ABANDONED"
    CHURN_FLAGGED    = "CHURN_FLAGGED"

class Channel(str, Enum):
    WHATSAPP = "WHATSAPP"; SMS = "SMS"; EMAIL = "EMAIL"; NONE = "NONE"

class RunMode(str, Enum):
    BASELINE = "BASELINE"; AGENT = "AGENT"; LIVE = "LIVE"
```

## Tables

### `customers`
| column | type | notes |
|---|---|---|
| `id` | text PK | `cus_...` |
| `name` | text | synthetic |
| `phone_e164` | text | synthetic, +91 |
| `email` | text | |
| `issuer_code` | text | e.g. `HDFC`, `SBIN` — joins to issuer health |
| `opted_out_at` | timestamptz null | set = never contact again |
| `segment` | text | `SALARIED_MONTH_START`, `SALARIED_MONTH_END`, `GIG_IRREGULAR`, `SELF_EMPLOYED` — **generator ground truth, never read by `core/`** |
| `created_at` | timestamptz | |

> `segment` exists for corpus generation and for post-hoc analysis in the eval
> report. A test asserts `core/` never selects this column.

### `mandates`
| column | type | notes |
|---|---|---|
| `id` | text PK | `mnd_...` |
| `customer_id` | text FK | |
| `rail` | text | `UPI_AUTOPAY` \| `ENACH` \| `CARD_RECURRING` |
| `status` | text | `ACTIVE` \| `REVOKED` \| `EXPIRED` \| `PAUSED` \| `AWAITING_REAUTH` |
| `max_amount_paise` | bigint | the mandate cap |
| `frequency` | text | `MONTHLY` \| `WEEKLY` \| `QUARTERLY` |
| `debit_day` | int | day-of-month for the scheduled charge |
| `valid_from` / `valid_until` | date | |
| `revoked_at` | timestamptz null | |
| `razorpay_subscription_id` | text null | test-mode id when live |

### `cycles`
One billing cycle per mandate per period. This is the unit the presentation cap
applies to.

| column | type | notes |
|---|---|---|
| `id` | text PK | `cyc_...` |
| `mandate_id` | text FK | |
| `period_start` / `period_end` | date | |
| `amount_paise` | bigint | |
| `state` | text | `SCHEDULED` \| `IN_RECOVERY` \| `RECOVERED` \| `ABANDONED` |
| `presentations_used` | int | incremented only on actual presentment |
| `recovered_at` | timestamptz null | |
| `recovered_via` | text null | `PRESENTMENT` \| `PAYMENT_LINK` |
| `recovered_amount_paise` | bigint null | |

### `attempts`
Every presentment, successful or not.

| column | type | notes |
|---|---|---|
| `id` | text PK | `att_...` |
| `cycle_id` | text FK | |
| `attempt_no` | int | 1-indexed within the cycle |
| `presented_at` | timestamptz | simulated time in eval mode |
| `succeeded` | bool | |
| `gateway_code` | text null | raw failure code |
| `gateway_desc` | text null | |
| `run_id` | text FK | isolates baseline from agent |

### `failure_events`
Normalised ingest output. One row per failed attempt.

| column | type | notes |
|---|---|---|
| `id` | text PK | `fev_...` |
| `attempt_id` | text FK unique | idempotency anchor |
| `mandate_id`, `cycle_id`, `customer_id` | text FK | denormalised for query speed |
| `raw_code` | text | |
| `amount_paise` | bigint | |
| `occurred_at` | timestamptz | |

### `classifications`
| column | type | notes |
|---|---|---|
| `id` | text PK | `cls_...` |
| `failure_event_id` | text FK | |
| `root_cause` | text enum | |
| `subtype` | text enum | |
| `disposition` | text enum | derived from cause, denormalised |
| `confidence` | numeric(3,2) | |
| `matched_rule` | text | which taxonomy row fired |

### `predictions`
| column | type | notes |
|---|---|---|
| `id` | text PK | `prd_...` |
| `failure_event_id` | text FK | |
| `curve` | jsonb | `[{"day_offset":0,"p":0.04}, ...]` 15 entries, day 0..14 |
| `best_day_offset` | int | argmax subject to policy constraints |
| `best_p` | numeric(4,3) | |
| `basis` | text | `CUSTOMER_HISTORY` \| `POPULATION_PRIOR` \| `BLENDED` \| `ISSUER_RECOVERY` |
| `feature_contributions` | jsonb | per-term weight for explainability |

### `decisions`
| column | type | notes |
|---|---|---|
| `id` | text PK | `dec_...` |
| `failure_event_id` | text FK | |
| `action_type` | text enum | |
| `scheduled_for` | timestamptz null | |
| `channel` | text enum | |
| `gate_result` | text enum | |
| `blocked_by` | jsonb null | list of `{check, code, message}` |
| `rationale` | text | one plain-English sentence, LLM-written, judge-readable |
| `inputs_snapshot` | jsonb | everything the decision saw — reproducibility |
| `run_id` | text FK | |

### `pending_actions`
The scheduler's work queue.

| column | type | notes |
|---|---|---|
| `id` | text PK | |
| `decision_id` | text FK | |
| `run_at` | timestamptz | simulated time in eval mode |
| `state` | text | `PENDING` \| `EXECUTED` \| `CANCELLED` \| `EXPIRED` |
| `cancelled_reason` | text null | e.g. `CUSTOMER_PAID`, `MANDATE_REVOKED` |

### `messages`
| column | type | notes |
|---|---|---|
| `id` | text PK | `msg_...` |
| `customer_id`, `cycle_id` | text FK | |
| `channel` | text enum | |
| `template_key` | text | must be in the approved allowlist |
| `variables` | jsonb | |
| `body_rendered` | text | |
| `sent_at` | timestamptz | |
| `suppressed` | bool | true if the gate blocked it |
| `suppressed_reason` | text null | |
| `run_id` | text FK | |

### `payment_links`
| column | type | notes |
|---|---|---|
| `id` | text PK | `pyl_...` |
| `cycle_id` | text FK | |
| `amount_paise` | bigint | |
| `razorpay_link_id` | text null | test mode |
| `short_url` | text null | |
| `created_at`, `expires_at` | timestamptz | |
| `paid_at` | timestamptz null | |
| `run_id` | text FK | |

### `issuer_health`
Ground truth outage windows, and the observable degraded-rate signal.

| column | type | notes |
|---|---|---|
| `issuer_code` | text | |
| `as_of_date` | date | |
| `observed_success_rate` | numeric(4,3) | what `core/` is allowed to see |
| `is_outage` | bool | **ground truth, generator only** |

`core/predict` may read `observed_success_rate`. A test asserts it never reads
`is_outage`.

### `ledger` — append-only
| column | type | notes |
|---|---|---|
| `id` | bigserial PK | monotonic, gives natural ordering |
| `ulid` | text unique | `led_...` |
| `occurred_at` | timestamptz | simulated time |
| `wall_clock_at` | timestamptz | real time the row was written |
| `event_type` | text enum | |
| `run_id` | text FK | |
| `mandate_id`, `cycle_id`, `customer_id` | text null | |
| `decision_id` | text null FK | |
| `amount_paise` | bigint null | signed; positive = recovered |
| `channel` | text null | |
| `rationale` | text | **never null** |
| `payload` | jsonb | full structured detail |
| `corrects_ledger_id` | bigint null | corrections are new rows |

```sql
CREATE OR REPLACE FUNCTION ledger_is_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'ledger is append-only (attempted %)', TG_OP;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_no_update BEFORE UPDATE OR DELETE ON ledger
FOR EACH ROW EXECUTE FUNCTION ledger_is_append_only();
```

### `runs`
| column | type | notes |
|---|---|---|
| `id` | text PK | `run_...` |
| `mode` | text enum | `BASELINE` \| `AGENT` \| `LIVE` |
| `corpus_id` | text | which generated corpus |
| `seed` | int | |
| `policy_config_hash` | text | hash of `policy.yaml` at run time |
| `started_at` / `finished_at` | timestamptz | |
| `metrics` | jsonb | the scored output |

### `contact_log`
Denormalised rate-limit ledger, so the gate does one indexed lookup.

| column | type | notes |
|---|---|---|
| `customer_id` | text | |
| `sent_at` | timestamptz | |
| `channel` | text | |
| `run_id` | text | |

Index: `(customer_id, run_id, sent_at DESC)`.

## Ground-truth tables — generator only

Never queried by `core/`. A test enforces this by scanning `core/` for the names.

### `funding_calendar`
| column | type | notes |
|---|---|---|
| `customer_id` | text | |
| `date` | date | |
| `balance_paise` | bigint | the true balance that day |

### `corpus_meta`
| column | type | notes |
|---|---|---|
| `id` | text PK | |
| `seed` | int | |
| `n_customers`, `n_mandates`, `n_cycles` | int | |
| `cause_mix` | jsonb | the intended distribution |
| `generated_at` | timestamptz | |

## Key invariants — write these as tests

1. `cycles.presentations_used` equals `COUNT(attempts WHERE cycle_id = ...)` for
   the same `run_id`.
2. No `attempts` row exists for a cycle whose mandate was `REVOKED` at
   `presented_at`.
3. Every `decisions` row has a non-empty `rationale`.
4. Every state-changing operation has at least one `ledger` row within the same
   transaction.
5. `SUM(ledger.amount_paise WHERE event_type IN (RECOVERED, LINK_PAID))` equals
   the run's reported recovered total.
6. `contact_log` count per customer per 7 simulated days never exceeds
   `policy.max_contacts_per_week`.
