# 07 — Synthetic Data Generator

**This is the load-bearing component.** If failures are drawn independently at
random, there is no timing signal to learn, the prediction layer collapses into
keyword matching on failure codes, the baseline comparison shows no delta, and
the entire submission is dead. Budget real time here — treat it as a first-class
deliverable, not a fixture.

The generator must produce a world in which **a smarter policy genuinely wins,
and a naive one genuinely loses**, for reasons that are causally legible.

---

## What the generator produces

1. `customers` with hidden `segment` and a hidden `funding_calendar`
2. `mandates` and `cycles`
3. `issuer_health` with correlated outage windows
4. A `bank.py` oracle that resolves any presentment against ground truth
5. `corpus_meta` recording the seed and intended distribution

`core/` sees only: the failure events, the observable issuer success rates, and
the customers' own prior *outcomes*. Never the calendar, never the segment,
never `is_outage`.

---

## Customer segments

Four, with distinct funding behaviour. Proportions are config.

### `SALARIED_MONTH_START` (~40%)
Credit on day 1–3 of the month, jittered ±1 day, shifted to the next working day
if it lands on a Sunday or bank holiday. Balance decays over the month; by day
22–28 a meaningful fraction cannot cover a ₹1,000+ debit.

**This is the segment the whole thesis rests on.** A failure on the 27th is
recoverable on the 2nd and *not* on the 29th. Fixed-interval T+1/T+3/T+5 burns
all three presentations inside the dead zone. Cadence waits.

### `SALARIED_MONTH_END` (~20%)
Credit on day 28–31. Same shape, phase-shifted. Included specifically so the
model cannot succeed by hardcoding "retry on the 2nd" — it has to actually read
per-customer history. Verify this: a model that ignores customer history should
score visibly worse on this cohort. Report per-segment recovery in the eval.

### `GIG_IRREGULAR` (~25%)
Small, frequent, weakly-periodic credits. Weekly-ish with high variance. Balance
is a noisy random walk with a low mean. Some cycles are genuinely unrecoverable.

Purpose: prevents an inflated headline. If every failure were recoverable with
perfect timing, the numbers would be a fantasy. This cohort is where the honest
ceiling comes from.

### `SELF_EMPLOYED_LUMPY` (~15%)
Large, sparse, aperiodic credits. Long dry spells punctuated by big inflows.

Purpose: the cohort where `basis = POPULATION_PRIOR` should correctly refuse to
commit, and where the payment-link fallback earns its keep.

---

## The funding calendar

Per customer, per simulated day, a true balance:

```
balance[d] = balance[d-1] + credits[d] - spend[d]
```

- `credits[d]` from the segment's credit process
- `spend[d]` a gamma-distributed daily draw scaled to segment income, with a
  spike immediately after each credit (people spend when paid)
- Floor at zero; a small share of customers carry a persistent near-zero balance

A presentment for amount `A` on day `d` succeeds on the balance test iff
`balance[d] >= A`. Deduct on success.

**The spend spike after credit is essential.** It creates a *narrow* window —
funded on day 2, drained by day 6 — which is what makes precise timing valuable
rather than a matter of merely waiting longer. Without it, "always retry on
day 14" wins and your model has nothing to add. Tune the spike until the optimal
retry window is roughly 2–4 days wide, then verify it with an oracle run (below).

---

## Issuer outages

Pick 4–6 issuer codes. For each, sample outage windows: 1–3 per simulated
quarter, each 6–36 hours, severity 0.3–0.95 (fraction of attempts that fail).

Critical property: **an outage hits every mandate on that issuer at once.** This
is the correlation that makes the classifier's co-occurrence check meaningful. If
outages were per-transaction coin flips, there would be nothing to diagnose.

Also emit `observed_success_rate` per issuer per day, computed from attempts
*plus* a background stream of synthetic traffic, so the signal exists even on
days when your own book had few attempts.

Include at least one **overlap case**: a genuine balance shortfall occurring
during an issuer outage on the same customer. This is the case where naive
logic picks the wrong intervention, and it is worth one slide.

---

## Cause mix

Target distribution over failure events. Config, so you can stress alternatives.

| Root cause | Share | Notes |
|---|---|---|
| `BALANCE_SHORTFALL` | 55% | the main path |
| `ISSUER_DEGRADED` | 12% | clustered, not independent |
| `TECHNICAL_TRANSIENT` | 8% | |
| `MANDATE_DEFECT` | 10% | revoked 5, expired 2, cap 2, frequency 1 |
| `INSTRUMENT_DEFECT` | 9% | closed 3, frozen 2, dormant 2, card expired 2 |
| `RISK_BLOCK` | 4% | |
| `UNKNOWN` / unmapped code | 2% | deliberately include codes absent from the taxonomy — the classifier must degrade gracefully, and you want at least one on screen |

The 22% terminal block (`MANDATE_DEFECT` + `INSTRUMENT_DEFECT`-dead +
`RISK_BLOCK`) is where the baseline wastes presentations and Cadence does not.
That gap is a large share of your uplift and it is entirely honest.

---

## Adversarial cases — plant these deliberately

Each one exists to produce a specific moment in the demo or the report.

| # | Case | What it proves |
|---|---|---|
| A1 | Failure on the 27th, customer funded on the 2nd | Core thesis. Baseline burns 3 attempts, Cadence waits and wins. |
| A2 | Mandate revoked mid-cycle, after the schedule was set | Gate re-check at execution time works. **This is the staged refusal.** |
| A3 | Customer pays via link while a presentment is pending | Cancellation logic; no double charge. |
| A4 | Issuer outage overlapping a real balance shortfall | Diagnosis over code-matching. |
| A5 | Failure on the 29th of a cycle ending the 31st | No feasible window; must skip to link, not force a doomed retry. |
| A6 | Customer opts out mid-recovery | All contact stops immediately, presentment may continue if lawful. |
| A7 | Charge above the mandate cap | Correctly terminal; escalate, do not present. |
| A8 | Same customer, two mandates, both failing | Contact cap applies per customer, not per mandate. Baseline double-messages. |
| A9 | Unmapped gateway code | Degrades to `UNKNOWN`/terminal, escalates, does not guess. |
| A10 | Two consecutive failed cycles | Churn flag fires, automation ceases. |
| A11 | Recovery that would land in quiet hours | Message deferred to morning, not suppressed entirely. |
| A12 | Dormant account reactivated after nudge | `RECOVERABLE_ACTION` path actually completes. |

Tag each in `corpus_meta` so the eval report can render a row per adversarial
case with pass/fail. That table is a strong artifact on its own.

---

## Splits

- **Train** (~40%): fit `gap_term`, tune weights, calibrate the population prior
- **Held-out** (~60%): every reported number

Split **by customer**, not by event. Splitting by event leaks a customer's salary
pattern from train into test and inflates everything. State the split rule out
loud in the demo — someone will ask, and having the right answer ready is worth
a lot.

---

## Scale

| Entity | Count |
|---|---|
| Customers | 300 |
| Mandates | 400 (some customers hold two) |
| Simulated days | 90 |
| Cycles | ~1,200 |
| Failed cycles | 220–280 |

The track bar says 50+; 200+ failures is comfortably above it and still runs in
seconds under `VirtualClock`.

---

## Validation — run these before trusting a single result

The generator is code, and code has bugs. These four checks catch the failure
modes that would silently invalidate the submission.

### V1 — Oracle run
Run a perfect-information policy that reads `funding_calendar` directly and
always presents on the optimal day. Its recovery rate is the ceiling.

- Ceiling near 100% → the world is too easy, no `GIG_IRREGULAR` difficulty.
  Increase spend rates and reduce credit sizes.
- Ceiling below ~60% → too hard; the model has little headroom to demonstrate.

Target: ceiling around 75–85%. Then Cadence should land meaningfully above the
baseline and meaningfully below the oracle. **Report all three.** Showing the
oracle is a confidence move: it says you know exactly how much of the available
signal you captured, and it pre-empts "how do we know this is good."

### V2 — Baseline must genuinely underperform
Run fixed-interval T+1/T+3/T+5. If it scores close to the oracle, the timing
signal is too weak — sharpen the post-credit spend spike.

### V3 — Signal audit
For `SALARIED_*` customers, plot success rate by day-of-month. It must show a
clear peak. If it is flat, the calendar is not doing what you think.

### V4 — Leakage grep
An automated test that scans `core/` for references to `funding_calendar`,
`segment`, `is_outage`, and any `sim.bank` import. Fails the build on a hit.

Run V1–V4 in CI. When a judge asks how you know the result is not an artifact of
your own data, you have four answers instead of a shrug.

---

## Reproducibility

Single `seed` threads through every random draw. `make corpus SEED=42` twice must
produce byte-identical output. Use explicit `numpy.random.Generator` instances
per subsystem, never global state — otherwise adding a call in one place silently
reshuffles everything downstream and yesterday's numbers stop reproducing at the
worst possible moment.
