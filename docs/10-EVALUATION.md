# 10 — Evaluation Harness

The track bar: *"show measured money recovered across a batch, with compliant
escalation, stopping rules, and an audit trail."* This document is how you satisfy
that in a way that survives questioning.

---

## Three arms, one world

| Arm | Policy | Purpose |
|---|---|---|
| `BASELINE` | Fixed interval T+1, T+3, T+5. No classification, no gate, generic dunning email on each failure. | What the merchant does today. |
| `AGENT` | Cadence. | The submission. |
| `ORACLE` | Perfect information: reads `funding_calendar`, presents on the optimal day, skips terminal cases. | The ceiling. |

All three run against the **same corpus, same seed, same `bank.py`, same
`VirtualClock`**. A test asserts the three runs issue identical queries to the
simulator interface. If the agent gets a friendlier world than the baseline, the
headline number is worthless and a sharp judge will find it.

### Building an honest baseline

Do not straw-man it. The baseline must be a *competent* version of the naive
approach:

- Retries on a fixed schedule, which is what most PSPs actually do
- Sends a dunning message on each failure, because merchants do
- Stops at the presentation cap, because the rail enforces that

What it does **not** have — and this is the honest, load-bearing difference:

- No root-cause classification, so it retries terminal cases
- No timing model, so it retries in the dead zone
- No compliance gate, so it breaches contact caps and quiet hours
- No fallback link, so exhausted cycles simply die

Label it in the UI as "fixed-interval retry, no gate." Say in the demo that you
built the baseline to be as strong as the real-world default, and name the four
things it lacks. Volunteering the comparison's limits is what makes the
comparison believable.

---

## Metrics

### Primary — money

| Metric | Definition |
|---|---|
| `recovered_paise` | Sum of amounts on cycles reaching `RECOVERED` |
| `recovery_rate` | Recovered cycles / failed cycles |
| `recovery_rate_recoverable` | Recovered / cycles the oracle proved recoverable. The fairer number — report both. |
| `at_risk_paise` | Total value of failed cycles entering recovery |
| `captured_of_headroom` | `(agent − baseline) / (oracle − baseline)` |

### Primary — cost of recovery

The metrics that make this a real submission rather than a recovery-rate contest.

| Metric | Definition |
|---|---|
| `presentments_total` | Regulated attempts consumed |
| `presentments_per_recovery` | Total / successful recoveries |
| `wasted_presentments` | Presentments against `TERMINAL` cases — pure waste |
| `messages_total` | Customer contacts |
| `messages_per_recovery` | |
| `customers_over_contacted` | Customers exceeding the weekly cap |
| `mean_days_to_recovery` | Failure to money-in |
| `link_conversion_rate` | Links paid / links sent |

### Compliance

| Metric | Definition |
|---|---|
| `checks_run` | Total gate evaluations |
| `actions_blocked` | Grouped by code |
| `violations` | Executed actions that would fail the gate, found by the **independent auditor** |

`violations` must be 0 for `AGENT`. It will be non-zero for `BASELINE`, which is
the point.

### Classifier

Per-cause precision and recall against generator ground truth, plus the confusion
matrix, plus the asymmetric error costs:

| Metric | Definition |
|---|---|
| `false_recoverable_cost_paise` | Presentments wasted by calling a terminal case recoverable |
| `false_terminal_cost_paise` | Revenue forgone by calling a recoverable case terminal |

Report these separately. Do not average them into an F1 — the asymmetry is the
interesting finding and collapsing it throws away your best material.

### Timing model

| Metric | Definition |
|---|---|
| `mean_days_from_optimal` | Distance between chosen day and the oracle's day |
| `hit_rate_within_2_days` | Fraction of predictions within 2 days of optimal |
| `calibration` | Predicted success probability vs realised, in deciles |

The calibration plot is a strong artifact. A model that says 60% and is right 60%
of the time is trustworthy in a way that a higher-accuracy uncalibrated model is
not, and very few hackathon teams will show one.

---

## The independent auditor

Separate module, `eval/auditor.py`. It reads the finished ledger and **re-derives
from scratch** whether every executed action was permissible, using its own
implementation of the rules — not by calling `core/compliance`.

Yes, this duplicates logic. That is the point. "Zero violations, verified by a
separate auditor that does not share code with the enforcement path" is a
materially stronger claim than "the gate says it blocked things," and it costs
about ninety minutes.

Output:
```json
{"rows_audited": 4821, "violations": [], "auditor_version": "1.0",
 "shares_code_with_gate": false}
```

---

## Report generation

`make report` produces `reports/{run_id}/index.html`:

1. Corpus summary: counts, cause mix, segment mix, split rule
2. The three-arm comparison table
3. Per-segment breakdown — this is where you prove the model reads customer
   history rather than hardcoding month-start. `SALARIED_MONTH_END` recovery
   should be comparable to `SALARIED_MONTH_START`. If it is much worse, the
   customer term is not working and you need to know before the judges do.
4. Adversarial case table: all 12 cases from `07`, pass/fail, with ledger links
5. Classifier confusion matrix and asymmetric costs
6. Calibration plot
7. Compliance report including the independent audit
8. Config appendix: policy version, weights, constants with their `source` field,
   seed, git SHA

Item 8 is what makes the whole thing reproducible rather than a claim.

---

## Statistical honesty

With ~250 failed cycles, differences of a few percentage points are noise.

- Run the full three-arm evaluation across **5 seeds** and report mean ± spread.
  This takes minutes under `VirtualClock` and pre-empts the single sharpest
  question available to a judge: *"is that just one lucky seed?"*
- Bootstrap a 95% confidence interval on the recovery-rate delta.
- If the interval on your uplift crosses zero, say so plainly and report what
  you would need to resolve it. A team that knows its result is underpowered
  reads as far more competent than one that quotes three decimal places on a
  single run.

---

## Reproducibility contract

```bash
make clean && make corpus SEED=42 && make eval SEED=42 && make report
```

From an empty database, this must reproduce every number in the deck. Run it once
the night before, then once more the morning of. `make demo` should be a single
command that a judge could run themselves.
