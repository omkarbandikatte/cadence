# 04 — Failure Taxonomy

The classifier's whole job: turn a noisy gateway/bank failure code into a
**disposition** that implies a different intervention. Codes are raw material.
Disposition is the answer.

## The four dispositions

| Disposition | Meaning | Presentment permitted? |
|---|---|---|
| `RECOVERABLE_TIMING` | Money will exist later. Timing is the entire problem. | Yes, at a predicted time |
| `RECOVERABLE_IMMEDIATE` | Transient technical fault. | Yes, after a short cooling-off |
| `RECOVERABLE_ACTION` | Needs the customer to do something first. | No, until the action completes |
| `TERMINAL` | Presenting again is useless or non-compliant. | **No** |

If the classifier is unsure, the disposition is `TERMINAL`. We do not retry what
we do not understand. This costs a little recovery and buys a lot of credibility.

## `config/taxonomy.yaml`

Structure. Populate the `codes` lists from the actual failure codes your test-mode
corpus emits — **verify against current Razorpay error-code documentation rather
than trusting this list verbatim**, since gateway codes are versioned and change.

```yaml
version: 1
default:
  root_cause: UNKNOWN
  subtype: NONE
  disposition: TERMINAL
  confidence: 0.0

rules:
  - id: BAL_001
    root_cause: BALANCE_SHORTFALL
    subtype: NONE
    disposition: RECOVERABLE_TIMING
    confidence: 0.95
    codes: [INSUFFICIENT_FUNDS, NACH_INSUFFICIENT_BALANCE, U30_BALANCE, BT_INSUFFICIENT]
    desc_contains: ["insufficient", "low balance", "not enough"]

  - id: ISS_001
    root_cause: ISSUER_DEGRADED
    subtype: ISSUER_DOWN
    disposition: RECOVERABLE_TIMING
    confidence: 0.85
    codes: [ISSUER_DOWN, BANK_UNAVAILABLE, U69, RB_DECLINED_UPSTREAM]
    desc_contains: ["issuer", "bank unavailable", "upstream"]
    # corroborated at classify time by issuer_health.observed_success_rate

  - id: TEC_001
    root_cause: TECHNICAL_TRANSIENT
    subtype: NONE
    disposition: RECOVERABLE_IMMEDIATE
    confidence: 0.80
    codes: [GATEWAY_TIMEOUT, NETWORK_ERROR, U16, RESPONSE_TIMEOUT]
    desc_contains: ["timeout", "temporarily unavailable"]

  - id: MND_REV
    root_cause: MANDATE_DEFECT
    subtype: REVOKED
    disposition: TERMINAL
    confidence: 1.00
    codes: [MANDATE_REVOKED, UMN_REVOKED, NACH_MANDATE_CANCELLED]

  - id: MND_EXP
    root_cause: MANDATE_DEFECT
    subtype: EXPIRED
    disposition: TERMINAL
    confidence: 1.00
    codes: [MANDATE_EXPIRED, UMN_EXPIRED]

  - id: MND_CAP
    root_cause: MANDATE_DEFECT
    subtype: AMOUNT_EXCEEDS_CAP
    disposition: TERMINAL
    confidence: 1.00
    codes: [AMOUNT_EXCEEDS_MANDATE, DEBIT_LIMIT_EXCEEDED]

  - id: MND_FRQ
    root_cause: MANDATE_DEFECT
    subtype: FREQUENCY_VIOLATION
    disposition: TERMINAL
    confidence: 1.00
    codes: [FREQUENCY_VIOLATION, DUPLICATE_DEBIT_IN_PERIOD]

  - id: INS_CLS
    root_cause: INSTRUMENT_DEFECT
    subtype: ACCOUNT_CLOSED
    disposition: TERMINAL
    confidence: 1.00
    codes: [ACCOUNT_CLOSED, INVALID_ACCOUNT, NO_SUCH_ACCOUNT]

  - id: INS_FRZ
    root_cause: INSTRUMENT_DEFECT
    subtype: ACCOUNT_FROZEN
    disposition: TERMINAL
    confidence: 0.95
    codes: [ACCOUNT_FROZEN, ACCOUNT_BLOCKED, DEBIT_FREEZE]

  - id: INS_DRM
    root_cause: INSTRUMENT_DEFECT
    subtype: ACCOUNT_DORMANT
    disposition: RECOVERABLE_ACTION
    confidence: 0.90
    codes: [ACCOUNT_DORMANT, ACCOUNT_INACTIVE]

  - id: INS_CRD
    root_cause: INSTRUMENT_DEFECT
    subtype: CARD_EXPIRED
    disposition: RECOVERABLE_ACTION
    confidence: 1.00
    codes: [CARD_EXPIRED, EXPIRED_CARD]

  - id: RSK_001
    root_cause: RISK_BLOCK
    subtype: NONE
    disposition: TERMINAL
    confidence: 0.90
    codes: [DO_NOT_HONOUR, RISK_DECLINE, FRAUD_SUSPECTED, SECURITY_VIOLATION]
```

## Classification algorithm

```
1. Exact match on raw_code against rules[].codes  -> return rule
2. Case-insensitive substring match of gateway_desc against rules[].desc_contains
   -> return rule with confidence * 0.8
3. Corroboration pass (ISSUER_DEGRADED only):
     if matched ISS_001 but issuer_health.observed_success_rate for this issuer
     today is within normal band, downgrade to UNKNOWN/TERMINAL and log the
     disagreement. A bank blaming its upstream while its upstream is fine is
     more likely a per-customer problem.
   Conversely, if code matched BAL_001 but the issuer's observed success rate has
     collapsed today, raise a co-occurrence flag on the classification — the
     retry timing should then follow issuer recovery, not the salary calendar.
4. No match -> default (UNKNOWN, TERMINAL, 0.0)
```

Step 3 is where the "diagnosis, not code-matching" claim becomes real. Build it.
It is roughly thirty lines and it is the single most defensible thing in the
classifier under questioning.

## Cause -> permitted actions

The policy table in `05` consumes this. Nothing outside these sets is legal.

| Root cause | Permitted actions |
|---|---|
| `BALANCE_SHORTFALL` | `PRE_DEBIT_NOTICE`, `TOPUP_NUDGE`, `SCHEDULE_PRESENTMENT`, `SEND_PAYMENT_LINK`, `STOP_MARK_CHURN` |
| `ISSUER_DEGRADED` | `WAIT_ISSUER_RECOVERY`, `SCHEDULE_PRESENTMENT`, `SEND_PAYMENT_LINK` |
| `TECHNICAL_TRANSIENT` | `PRESENT_NOW` (after cooling-off), `SCHEDULE_PRESENTMENT` |
| `MANDATE_DEFECT` | `REQUEST_REAUTH`, `SEND_PAYMENT_LINK`, `ESCALATE_TO_MERCHANT`, `NO_ACTION` |
| `INSTRUMENT_DEFECT` (`CARD_EXPIRED`, `ACCOUNT_DORMANT`) | `REQUEST_INSTRUMENT_UPDATE`, `SEND_PAYMENT_LINK` |
| `INSTRUMENT_DEFECT` (`ACCOUNT_CLOSED`, `ACCOUNT_FROZEN`) | `SEND_PAYMENT_LINK`, `ESCALATE_TO_MERCHANT`, `STOP_MARK_CHURN` |
| `RISK_BLOCK` | `ESCALATE_TO_MERCHANT`, `NO_ACTION` — **never auto-contact the customer** |
| `UNKNOWN` | `ESCALATE_TO_MERCHANT`, `NO_ACTION` |

Note `RISK_BLOCK`. A bank declining for suspected fraud is not a dunning
opportunity, and messaging that customer could interfere with a fraud
investigation. Handing it to a human is the correct answer, and saying so in the
demo shows you thought about the failure modes that aren't about revenue.

## Metrics the classifier must report

Because you have generator ground truth, you can score this honestly:

- Per-cause precision and recall against `corpus.ground_truth_cause`
- Confusion matrix, rendered in the eval report
- **Cost-weighted error**: a `TERMINAL` case misclassified as `RECOVERABLE` costs
  a wasted regulated presentation and a customer contact. A `RECOVERABLE` case
  misclassified as `TERMINAL` costs the whole cycle's revenue. Report both
  directions separately with rupee amounts attached. Do not average them into a
  single F1 — the asymmetry is the interesting part.
