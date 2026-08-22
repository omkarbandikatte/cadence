# 05 — Decision Engine

Two parts, deliberately separated:

- **The funding-window model** — *when* is the money likely to be there?
- **The policy table** — given cause, timing and state, *what* do we do?

The model is statistical and explainable. The policy is a table and testable.
Neither is an LLM. Judges will probe this; the answer is that a decision affecting
someone's bank account should be reproducible and auditable, and a table is both.

---

## Part A — The funding-window model

### Output

A 15-element curve, day offsets 0 through 14 from the failure, each a probability
that a presentment on that day succeeds. Plus `best_day_offset`, `basis`, and
per-term contributions.

### Why a hazard model and not a neural net

Three reasons, and say all three if asked:

1. **Data volume.** Per customer we have a handful of prior successes. A deep
   model on that is memorisation with extra steps.
2. **Explainability is a stated requirement** of the track. Every rupee moved
   needs a reason. A weighted sum of four named terms produces the reason for
   free.
3. **The signal is genuinely simple.** Indian salary credits are strongly
   periodic. The hard part is not model capacity, it is handling customers with
   no history and knowing when the periodic prior does not apply.

### Score

For each day offset `d` in 0..14, with calendar date `D = failure_date + d`:

```
score(d) = w_cust * customer_term(D)
         + w_pop  * population_term(D)
         + w_gap  * gap_term(d)
         + w_iss  * issuer_term(D)
         - w_pen  * proximity_penalty(d)
```

Normalise scores across the window to get the probability curve. Persist every
term's value in `feature_contributions` — this is what the dashboard renders when
a judge clicks "why this day."

#### `customer_term(D)` — the salary calendar

From this customer's prior **successful** debits (across all mandates), build a
day-of-month histogram, smoothed with a circular Gaussian kernel (sigma ≈ 1.5
days, because salary credits slip across weekends and holidays). Evaluate at
`day_of_month(D)`.

Confidence gate: fewer than `min_history_successes` (default 3) prior successes
→ `w_cust = 0` and `basis = POPULATION_PRIOR`. Do not pretend to know.

Also fold in **weekend and bank-holiday shifting**: if the histogram peak falls
on a Sunday, shift mass to the following Monday. Salary credited Friday is often
consumed by Monday, so for `SALARIED` patterns the useful window is the credit
day plus zero to two days, not plus five.

#### `population_term(D)` — the prior for strangers

A fixed day-of-month distribution over 1..31 with mass concentrated at month
start and a secondary bump at month end. Ship it as a config array so it is
inspectable and tunable, not buried in code:

```yaml
population_dom_prior: [0.055, 0.075, 0.080, 0.072, 0.060, 0.045, 0.035, ...]
```

Optionally condition on merchant category. A ₹149 OTT subscription and a ₹4,999
insurance premium do not fail for the same population.

#### `gap_term(d)` — empirical recovery hazard

From the corpus (or, in production, from history): given a `BALANCE_SHORTFALL`
failure, what fraction of eventual recoveries happened exactly `d` days later?
This captures the base rate independent of calendar position. Fit once at startup
over the training slice; **never fit on the held-out set.**

#### `issuer_term(D)` — outage recovery

If the co-occurrence flag from the classifier is set, or the issuer's observed
success rate is depressed, this term dominates: near-zero for days while the rate
is still depressed, rising as it recovers. When this term dominates, `basis`
becomes `ISSUER_RECOVERY` and the salary calendar is ignored — an outage does not
care what day of the month it is.

#### `proximity_penalty(d)` — don't retry too fast

Small monotonic penalty on very small `d`, encoding that a presentment one day
after an insufficient-funds failure is usually a wasted regulated attempt. This
is exactly the behaviour the baseline exhibits, and this term is the mechanism by
which you beat it.

### Constrained argmax

`best_day_offset` is not the raw argmax. It is:

```
argmax over d of score(d)
  subject to:
    d >= policy.min_cooling_off_days
    D <= cycle.period_end - policy.reserve_days
    D is presentable given the pre-debit notice lead time
    D is not a known non-processing day for the rail
```

If the feasible set is empty, the policy layer must skip presentment entirely and
go to the payment-link path. Handle this — it will happen for failures late in a
cycle and it is a good thing to show.

### Tuning the weights

Grid search on the **training** slice of the corpus, maximising recovered rupees
per presentation consumed. Freeze the weights, write them into `policy.yaml`, and
report held-out numbers only. Log the chosen weights in the run record so the
result is reproducible.

---

## Part B — The policy table

Input: `(root_cause, subtype, attempt_no, cycle_state, days_left_in_cycle,
prediction, prior_blocks)`. Output: an ordered candidate list; the first that
clears the gate wins.

### `config/policy.yaml` — decision rules

```yaml
policy_version: 3

rules:

  # ---- BALANCE_SHORTFALL: the main path ----
  - id: BAL_A1
    when: {cause: BALANCE_SHORTFALL, attempt_no: 1, feasible_window: true}
    candidates:
      - {action: PRE_DEBIT_NOTICE, offset_days_before_presentment: 2,
         channel: WHATSAPP, template: predebit_notice_v1}
      - {action: SCHEDULE_PRESENTMENT, at: prediction.best_day_offset}

  - id: BAL_A2
    when: {cause: BALANCE_SHORTFALL, attempt_no: 2, feasible_window: true}
    candidates:
      - {action: TOPUP_NUDGE, offset_days_before_presentment: 1,
         channel: WHATSAPP, template: topup_nudge_v1}
      - {action: SCHEDULE_PRESENTMENT, at: prediction.second_best_day_offset}

  - id: BAL_A3_EXHAUSTED
    when: {cause: BALANCE_SHORTFALL, presentations_exhausted: true}
    candidates:
      - {action: SEND_PAYMENT_LINK, channel: WHATSAPP,
         template: payment_link_v1, expiry_days: 5}
      - {action: STOP_MARK_CHURN, after_days: 6}

  - id: BAL_NO_WINDOW
    when: {cause: BALANCE_SHORTFALL, feasible_window: false}
    candidates:
      - {action: SEND_PAYMENT_LINK, channel: WHATSAPP, template: payment_link_v1}

  # ---- ISSUER_DEGRADED: not the customer's fault ----
  - id: ISS_A1
    when: {cause: ISSUER_DEGRADED}
    candidates:
      - {action: WAIT_ISSUER_RECOVERY, max_wait_days: 3}
      - {action: SCHEDULE_PRESENTMENT, at: prediction.best_day_offset}
    # deliberately no customer message: telling someone their bank is down
    # generates support load and does not change the outcome

  - id: ISS_A2_PERSISTENT
    when: {cause: ISSUER_DEGRADED, waited_days_gte: 3}
    candidates:
      - {action: SEND_PAYMENT_LINK, channel: WHATSAPP, template: payment_link_v1}
      # link routes through a different rail, which is the actual fix

  # ---- TECHNICAL_TRANSIENT ----
  - id: TEC_A1
    when: {cause: TECHNICAL_TRANSIENT, attempt_no_lte: 2}
    candidates:
      - {action: PRESENT_NOW, after_minutes: 90}

  # ---- MANDATE_DEFECT ----
  - id: MND_REV
    when: {cause: MANDATE_DEFECT, subtype: REVOKED}
    candidates:
      - {action: REQUEST_REAUTH, channel: WHATSAPP, template: reauth_v1}
      - {action: ESCALATE_TO_MERCHANT}
    forbid: [PRESENT_NOW, SCHEDULE_PRESENTMENT]

  - id: MND_CAP
    when: {cause: MANDATE_DEFECT, subtype: AMOUNT_EXCEEDS_CAP}
    candidates:
      - {action: ESCALATE_TO_MERCHANT, note: "mandate cap below charge amount;
         requires new mandate at a higher cap or a reduced charge"}
      - {action: SEND_PAYMENT_LINK, channel: WHATSAPP, template: payment_link_v1}
    forbid: [PRESENT_NOW, SCHEDULE_PRESENTMENT]

  # ---- INSTRUMENT_DEFECT ----
  - id: INS_UPD
    when: {cause: INSTRUMENT_DEFECT, subtype_in: [CARD_EXPIRED, ACCOUNT_DORMANT]}
    candidates:
      - {action: REQUEST_INSTRUMENT_UPDATE, channel: WHATSAPP,
         template: instrument_update_v1}
      - {action: SEND_PAYMENT_LINK, channel: WHATSAPP, template: payment_link_v1}
    forbid: [PRESENT_NOW, SCHEDULE_PRESENTMENT]

  - id: INS_DEAD
    when: {cause: INSTRUMENT_DEFECT, subtype_in: [ACCOUNT_CLOSED, ACCOUNT_FROZEN]}
    candidates:
      - {action: SEND_PAYMENT_LINK, channel: WHATSAPP, template: payment_link_v1}
      - {action: STOP_MARK_CHURN, after_days: 5}
    forbid: [PRESENT_NOW, SCHEDULE_PRESENTMENT]

  # ---- RISK_BLOCK and UNKNOWN: humans only ----
  - id: RSK
    when: {cause_in: [RISK_BLOCK, UNKNOWN]}
    candidates:
      - {action: ESCALATE_TO_MERCHANT}
    forbid: [PRESENT_NOW, SCHEDULE_PRESENTMENT, PRE_DEBIT_NOTICE,
             TOPUP_NUDGE, SEND_PAYMENT_LINK, REQUEST_REAUTH]

fallback:
  candidates: [{action: NO_ACTION}]
```

### Cancellation rules

A pending action is cancelled, not executed, when:

| Trigger | Cancel | Reason code |
|---|---|---|
| Cycle recovered by any route | all pending for that cycle | `CUSTOMER_PAID` |
| Mandate revoked | all presentments | `MANDATE_REVOKED` |
| Customer opted out | all messages | `OPTED_OUT` |
| Cycle period ended | all presentments | `CYCLE_CLOSED` |
| Payment link paid | all presentments and nudges | `LINK_PAID` |

Cancellation writes a ledger row. A cancelled over-contact is a metric you get to
report: *"the agent stood down N times because the customer had already paid."*

### Stopping rules — hard

- Presentations used `>= policy.max_presentations_per_cycle` → no more.
- `policy.max_consecutive_failed_cycles` cycles failed in a row → `STOP_MARK_CHURN`,
  hand to merchant, cease all automated contact.
- Any dispute or chargeback flag on the cycle → freeze everything immediately.
- `customers.opted_out_at` set → no contact, ever, on any channel.

### The rationale string

Every decision gets one sentence a judge can read without training. Generate it
from the structured record with a cached LLM call; on any failure, fall back to a
deterministic template. The LLM never changes the decision.

Good:
> Waiting until 2 Feb to re-present ₹1,499 because this customer's last four
> debits all cleared between the 2nd and the 4th, and today is the 27th.

> Not re-presenting: the mandate was revoked on 18 Jan. Sent a re-authorisation
> link instead.

> Skipping the reminder: this customer has already had two messages this week.

Bad:
> Action scheduled per policy BAL_A1 with confidence 0.87.
