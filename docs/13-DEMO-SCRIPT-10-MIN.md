# Cadence — 10-minute demo script

This script follows the recorded Cadence product walkthrough and expands it into
a ten-minute presentation. The goal is to show three things clearly: the
recovery problem, the measurable improvement, and the controls that prevent an
improper action.

## Before you start

- Open the landing page at `/`.
- Have the dashboard ready at `/app/compare` or the Run comparison screen.
- Keep the recorded demo available as a backup.
- Use the numbers currently visible in the run comparison screen. Do not read
  numbers from an older report if the selected run has changed.
- If demonstrating a live injection, use a seeded run and explain that the
  result is deterministic.

## 0:00–1:00 — The problem

**Screen:** Landing page. Leave the opening headline visible.

> Every recurring payment failure is not the same failure. A customer can be
> short on balance, a bank rail can be degraded, a mandate can be revoked, or
> the payment can be blocked for risk. But most retry systems treat these cases
> as one calendar: try again tomorrow, then try again in a few days, then stop.
>
> That approach misses the question that matters for a balance failure: when is
> the money actually likely to be available? It also creates a second problem:
> a retry may be operationally possible but still not be compliant.
>
> Cadence is a recovery system for recurring debits such as UPI Autopay and
> e-NACH. It answers three questions for every failure: why did it fail, when is
> the customer most likely to be funded, and are we allowed to act right now?

**Pause for two seconds.**

> The product is designed around bounded recovery: every action must be
> permitted, explainable, and recorded for audit.

## 1:00–2:15 — What Cadence does

**Screen:** Scroll to “How it works.”

> The workflow has six stages, and every stage is logged.
>
> First, ingest receives a webhook or a replayed event and normalises it into a
> single failure event. Second, classify maps the gateway or bank code to a root
> cause using a deterministic taxonomy. We do not ask a language model to guess
> what a failure means.
>
> Third, predict estimates the funding window from successful debit history and
> population priors. For a revoked mandate or terminal risk case, timing is not
> the problem, so this stage is skipped.
>
> Fourth, policy combines the cause, funding window, attempt count, and cycle
> state to propose a bounded action: retry, notify, create a link, re-authorise,
> or stop.
>
> Fifth is the compliance gate. This is the important architectural decision:
> the gate is the single choke point between a proposal and any real action.
>
> Sixth, execution calls an adapter and writes the result to the append-only
> ledger. That result becomes history for later predictions.

**Point at the Gate card.**

> Policy can recommend an action. It cannot authorise one. Only the gate can do
> that.

## 2:15–3:15 — The compliance guarantee

**Screen:** Scroll to “The gate is not advisory” and “Every decision is explainable.”

> The gate is not a warning banner and it is not a post-processing report. No
> code path may present a debit or send a message without passing through
> `compliance.evaluate()`.
>
> The checks are re-run at execution time, because the world may change after a
> decision is scheduled. The mandate may be revoked, the customer may opt out,
> the contact cap may be reached, or the required pre-debit notice may be
> missing. In those cases, the result is a normal blocked outcome, with the
> reasons written to the ledger.
>
> The second guarantee is explainability. Each decision records its inputs, the
> rule or score that fired, and a plain-English rationale.

> The language model is deliberately outside the decision path. It may help
> write a rationale, compose an approved message, or answer a read-only merchant
> question. It never chooses whether money should be presented.

## 3:15–4:30 — The headline result

**Screen:** Scroll to the results summary.

> Now let us look at the evaluation rather than making a product claim in the
> abstract.
>
> The baseline, Cadence, and oracle run on the same synthetic batch and through
> the same simulator. The baseline represents fixed-interval retry. The oracle
> is a ground-truth ceiling with information the agent would not have in a real
> deployment.

**Point to the visible table. Read the selected run’s exact values.**

> In this run, the baseline recovery rate is [BASELINE_RATE]. Cadence reaches
> [CADENCE_RATE], while the oracle reaches [ORACLE_RATE]. The important comparison
> is not only the recovery percentage. We also measure how many presentments and
> messages were used, how much was wasted on terminal cases, and whether any
> compliance violations occurred.

> Cadence records zero compliance violations in this comparison. That is not
> because blocked actions disappear. It is because blocked actions are handled
> explicitly and recorded as part of the result.

**Use the visible summary sentence if present.**

> The summary below the table expresses the result in operational terms: how
> much of the headroom Cadence captured and how many fewer regulated
> presentments it used.

## 4:30–6:00 — The timing model

**Screen:** Open the Run comparison screen and show the month strip.

> This month strip is the core of the timing idea. Each bar represents the
> historical probability that a debit clears on that day of the month for the
> selected customer. The markers show where the baseline and Cadence would make
> their attempts.

> A calendar retry does not know whether the customer is in a low-balance part
> of the month. It simply spends another attempt at a fixed offset. Cadence uses
> the customer's observed history to move the attempt toward the funding peak,
> subject to the policy and compliance constraints.

> Notice what this model is not doing. It is not reading the customer's current
> bank balance. It is not using a hidden future signal. It is estimating a
> funding window from information available in the recovery workflow.

> Its basis can be customer history, a population prior, a blended estimate, or
> issuer recovery. The decision row shows which basis dominated.

**Pause on the graph.**

> Cadence retries when timing is the problem, and stops or changes instruments
> when it is not.

## 6:00–7:15 — From portfolio to one cycle

**Screen:** Open Portfolio, then Cycles.

> The portfolio separates failed work, cycles in recovery, recovered value, and
> cases that need a human.

> The failure breakdown is also important. Balance shortfall is only one cause.
> Mandate defects, instrument defects, issuer degradation, technical failures,
> and risk blocks need different interventions.

> I can move from the portfolio to the cycles list and select one cycle. The
> cycle view gives the operator the complete story: customer and mandate,
> amount, state, presentations used, diagnosis, prediction basis, and the event
> timeline.

**Open one recovered or in-recovery cycle.**

> This is where the system becomes inspectable: failure, classification,
> prediction, decision, gate result, execution, and outcome in order.

## 7:15–8:30 — A blocked action is a success

**Screen:** Cycle timeline or a seeded injected case.

> Let us take the case where the mandate changes after the action was scheduled.
> I will revoke the mandate, or load the seeded revoked-mandate case, before the
> scheduled presentment runs.

**Trigger the case.**

> The agent re-checks the gate at execution time. It refuses to present because
> the mandate is no longer active. The refusal is written to the ledger with the
> block code and a human-readable reason.

> The system can still choose a compliant recovery path, such as re-authorisation
> or an approved payment link.

> Notice that the blocked row is neutral, not an application error. A block is a
> valid result. In payments, restraint is part of correctness.

## 8:30–9:15 — Ledger and escalation

**Screen:** Ledger, then return to Portfolio or the cycle timeline.

> The append-only ledger contains decisions, gate blocks, messages, presentments,
> links, recoveries, and abandoned outcomes. An auditor can filter blocked
> actions and see every failed check.

> The dashboard also hands work back to people. Risk blocks, unknown causes,
> mandate-cap mismatches, and repeated failed cycles belong in a needs-you queue.
> We do not keep contacting a customer when the right answer is investigation,
> a new mandate, or a human decision.

> Recover where recovery is justified, and stop cleanly where it is not.

## 9:15–10:00 — Limits and close

**Screen:** Return to Run comparison or landing page.

> Three limitations are worth stating clearly.
>
> First, this evaluation uses synthetic data. It makes the timing problem
> measurable, but is not a claim about a live merchant book.
>
> Second, regulatory constants are configuration, not hardcoded assumptions.
> Each policy constant carries a source and any unverified value is labelled as
> unverified before a real deployment.
>
> Third, the decision path is deterministic and interpretable. For money movement
> and customer contact, an auditable model is more useful than an opaque one.

> Cadence is a scheduling and decision layer around payment primitives: webhooks,
> subscriptions, pre-debit notifications, payment links, and re-authorisation.
> The same core logic runs in evaluation and live modes; only the clock and
> adapters change.
>
> Cadence diagnoses the cause, predicts the right window when timing matters,
> checks the action at the last responsible moment, and leaves a complete audit
> trail.
>
> That is Cadence. Thank you.

## Keep ready for Q&A

- **Is this one lucky run?** Re-run baseline and agent across multiple seeds and
  report the mean, spread, and confidence interval.
- **Does the language model control money movement?** No. Policy and prediction
  choose the proposal; the gate authorises or blocks it. The language model is
  limited to rationale writing, approved message composition, and read-only Q&A.
- **Why does the baseline show violations?** It represents fixed-interval retry
  without Cadence’s gate. Cadence’s zero is independently audited from the
  ledger, not produced by hiding invalid actions.
- **What happens to an unknown failure code?** It fails closed. Cadence does not
  retry what it does not understand.
- **What comes next?** Learn the funding curve online, add a real issuer-health
  signal, and validate policy constants against current regulatory circulars.