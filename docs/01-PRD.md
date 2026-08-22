# 01 — Product Requirements

## Problem

A merchant on Razorpay runs subscriptions collected via UPI Autopay and e-NACH.
A meaningful share of scheduled debits fail. Today the response is a fixed retry
calendar plus a generic dunning email. That approach has four defects:

1. **It ignores timing.** The dominant failure reason is insufficient balance,
   which is transient and periodic. A retry two days after a failure that lands
   three days before the customer's salary credit is a wasted presentation — and
   presentations are a capped, regulated resource.
2. **It treats all failures identically.** A revoked mandate, an expired card, an
   issuer outage and an empty account need four different responses. Retrying a
   revoked mandate is not merely useless, it is non-compliant.
3. **It gives up at the wrong boundary.** When presentations are exhausted the
   subscription is marked failed and the customer churns — even though the
   customer would happily pay via a link.
4. **It is unauditable.** When a merchant asks "why did you charge my customer
   four times in six days," nobody can answer from a system of record.

## What we build

An agent that closes the loop for one failure class end to end:

`detect -> classify root cause -> predict funding window -> gate against policy ->
execute bounded intervention -> log -> stop`

## Users

| User | What they need |
|---|---|
| **Merchant finance ops** | Recovered revenue, and an answer to "what did you do to my customer and why." |
| **Merchant support** | To see, per customer, the next scheduled action and how to cancel it. |
| **Razorpay risk/compliance** | Proof that presentation caps, notice periods, quiet hours and opt-outs are enforced structurally, not by convention. |
| **The end customer** | Not to be spammed, and to be told the amount and date *before* money leaves their account. |

## In scope

- Ingest of failed recurring debit events (webhook + batch replay).
- Root-cause classification across the taxonomy in `04`.
- Per-customer funding-window prediction with an explicit population fallback.
- A policy table mapping cause to permitted interventions.
- A compliance gate enforced on every action.
- Pre-debit notification via WhatsApp with SMS fallback.
- Re-presentment against the mandate, within caps.
- Payment Link fallback after presentations are exhausted.
- Re-authorisation link for mandate-defect cases.
- Append-only ledger with rationale on every row.
- A merchant dashboard: portfolio view, mandate timeline, ledger, run comparison.
- An evaluation harness running baseline and agent over the same corpus.
- Natural-language Q&A over the ledger (read-only).

## Out of scope — say this out loud in the demo

- **Live money.** Test mode only. Debit outcomes come from the simulator.
- **Card-network tokenisation and AFA flows.** We model the constraints, we do
  not implement the cryptography.
- **Voice.** Hinglish voice recovery is a listed track direction and a tempting
  add. It is out. It eats a full day and does not move the headline metric.
- **Multi-merchant tenancy.** Single merchant, single currency (INR).
- **Deep learning.** The timing model is an interpretable hazard model. See `05`
  for why this is a feature, not a shortcut.

## Success criteria

The build succeeds if, on a held-out corpus of 200+ failed debits, we can show:

| # | Criterion | Target |
|---|---|---|
| S1 | Recovery rate uplift over fixed-interval baseline | strictly positive and explained |
| S2 | Rupees recovered, agent vs baseline | reported side by side |
| S3 | Presentations consumed per successful recovery | lower than baseline |
| S4 | Customer messages sent per successful recovery | reported, and capped |
| S5 | Compliance violations | exactly 0 |
| S6 | Terminal-cause cases where we correctly did *not* retry | reported as a count |
| S7 | Reproducibility | same seed, same numbers, from empty DB |

S5 and S6 matter as much as S1. An agent that recovers more money by
over-presenting has not solved the problem, it has moved the cost.

## Explicit non-goal

We are not trying to maximise recovery rate. We are trying to maximise recovered
rupees **per unit of customer contact and per regulated presentation**. Say this
in the demo — it is the sentence that separates this from the other submissions.
